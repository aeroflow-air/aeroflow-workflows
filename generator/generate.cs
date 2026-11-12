#!/usr/bin/env -S dotnet --
#:package YamlDotNet@18.1.0
#:package JsonSchema.Net@9.6.0
#:property PublishAot=false
#:property Nullable=enable

// Generate a Bicep composition from a workload.yaml (ADR-0009).
//
// C# port of generate.py (.NET 10 file-based app). Same CLI, same rules,
// byte-identical output (checked against tests/generator/golden by
// tests/generator/run_csharp_golden.sh).
//
// Usage:
//   dotnet run generator/generate.cs -- --manifest workload.yaml --out-dir out [--local-modules DIR]

using System.Globalization;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Json.Schema;
using YamlDotNet.Core;
using YamlDotNet.RepresentationModel;

return Generator.Run(args);

/// <summary>A manifest the generator refuses. The message is shown to the caller.</summary>
sealed class ManifestError(string message) : Exception(message);

record Subscription(string Topic, string Name);

static class Generator
{
    const string GeneratorVersion = "0.1.0";
    const string HostingModule = "container-app-service";
    static readonly HashSet<string> NotYetSupported = ["store"];

    // ADR-0019 topic ownership: the only publisher of a <domain>-events topic.
    static readonly Dictionary<string, string> TopicOwners = new()
    {
        ["flight-events"] = "flight-simulator",
        ["gate-events"] = "svc-gate-allocation",
        ["baggage-events"] = "svc-baggage-reclaim",
    };

    // Azure Service Bus data-plane built-in roles.
    const string SbSenderRole = "69a216fc-b8fb-44d8-bc22-1f3c2cd27a39";
    const string SbReceiverRole = "4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0";

    // Matches container-app-service's own `name` constraints (2-28 chars).
    static readonly Regex AppName = new(@"^[a-z][a-z0-9-]{1,27}$");
    static readonly Regex Pin = new(@"^(?:br/platform:|br:ghcr\.io/aeroflow-air/)([a-z][a-z0-9-]*):(\d+\.\d+\.\d+)$");

    static string Root([CallerFilePath] string path = "") => Path.GetFullPath(Path.Combine(Path.GetDirectoryName(path)!, ".."));
    static string SchemaPath => Path.Combine(Root(), "schemas", "workload.schema.json");

    // ---- load and validate -------------------------------------------------

    public static JsonObject LoadManifest(string path)
    {
        JsonNode? data;
        try
        {
            var stream = new YamlStream();
            stream.Load(new StringReader(File.ReadAllText(path, Encoding.UTF8)));
            data = stream.Documents.Count == 0 ? null : ToJson(stream.Documents[0].RootNode);
        }
        catch (YamlException ex)
        {
            throw new ManifestError($"{path}: not valid YAML: {ex.Message}");
        }
        Validate(data);
        return (JsonObject)data!;
    }

    // YAML -> JSON with yaml.safe_load-style scalar typing, so the schema sees
    // the same types Python does (e.g. an unquoted 1 is a number, not a string).
    static JsonNode? ToJson(YamlNode node) => node switch
    {
        YamlMappingNode map => new JsonObject(map.Children.Select(kv =>
            KeyValuePair.Create(((YamlScalarNode)kv.Key).Value ?? "", ToJson(kv.Value)))),
        YamlSequenceNode seq => new JsonArray(seq.Children.Select(ToJson).ToArray()),
        YamlScalarNode s => Scalar(s),
        _ => null,
    };

    static JsonNode? Scalar(YamlScalarNode s)
    {
        var v = s.Value ?? "";
        if (s.Style is ScalarStyle.SingleQuoted or ScalarStyle.DoubleQuoted or ScalarStyle.Literal or ScalarStyle.Folded)
            return JsonValue.Create(v);
        if (v is "" or "~" or "null" or "Null" or "NULL") return null;
        if (Regex.IsMatch(v, "^(true|True|TRUE|yes|Yes|YES|on|On|ON)$")) return JsonValue.Create(true);
        if (Regex.IsMatch(v, "^(false|False|FALSE|no|No|NO|off|Off|OFF)$")) return JsonValue.Create(false);
        if (Regex.IsMatch(v, @"^[-+]?[0-9][0-9_]*$") && long.TryParse(v.Replace("_", ""), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var i))
            return JsonValue.Create(i);
        if (Regex.IsMatch(v, @"^[-+]?([0-9][0-9_]*)?\.[0-9_]*([eE][-+][0-9]+)?$") && double.TryParse(v.Replace("_", ""), NumberStyles.Float, CultureInfo.InvariantCulture, out var d))
            return JsonValue.Create(d);
        return JsonValue.Create(v);
    }

    public static void Validate(JsonNode? data)
    {
        var schema = JsonSchema.FromText(File.ReadAllText(SchemaPath, Encoding.UTF8));
        var element = JsonSerializer.SerializeToElement(data);
        var result = schema.Evaluate(element, new EvaluationOptions { OutputFormat = OutputFormat.List });
        if (result.IsValid) return;
        var lines = (result.Details ?? [])
            // Drop the `if` probe (its failure is not an error) and keyword summaries
            // such as "properties"/"allOf" that only restate the leaf errors.
            .Where(d => d.Errors is { Count: > 0 } && !d.EvaluationPath.ToString().Contains("/if"))
            .SelectMany(d => d.Errors!.Where(e => e.Key is not ("properties" or "allOf" or "items" or "then")).Select(e => (Path: d.InstanceLocation.ToString().TrimStart('/'), Message: e.Value)))
            .Distinct()
            .OrderBy(e => e.Path, StringComparer.Ordinal)
            .Select(e => $"  {(e.Path.Length == 0 ? "(root)" : e.Path)}: {e.Message}")
            .ToList();
        if (lines.Count == 0) lines.Add("  (root): does not match the schema");
        throw new ManifestError("workload.yaml does not match the schema:\n" + string.Join("\n", lines));
    }

    // ---- helpers -----------------------------------------------------------

    static List<string> Strings(JsonNode? node) =>
        node is JsonArray a ? a.Select(x => x!.GetValue<string>()).ToList() : [];

    /// <summary>Bicep-safe symbol fragment: baggage-events -> BaggageEvents.</summary>
    static string Symbol(string name) => string.Concat(
        name.Replace("_", "-").Split('-', StringSplitOptions.RemoveEmptyEntries)
            .Select(p => char.ToUpperInvariant(p[0]) + p[1..].ToLowerInvariant()));

    /// <summary>Validate the events: block (ADR-0019) and return (publishes, subscribes).</summary>
    public static (List<string> Publishes, List<Subscription> Subscribes) EventsOf(JsonObject manifest)
    {
        var caps = Strings(manifest["capabilities"]);
        if (manifest["events"] is not JsonObject events)
        {
            if (caps.Contains("queue"))
                throw new ManifestError(
                    "capability queue needs an events: block saying what the workload publishes and " +
                    "subscribes to (ADR-0019); queue on its own wires nothing.");
            return ([], []);
        }
        if (!caps.Contains("queue"))
            throw new ManifestError("events: needs the queue capability (ADR-0019).");

        var workload = manifest["workload"]!.GetValue<string>();
        var publishes = Strings(events["publishes"]);
        foreach (var topic in publishes)
        {
            if (!TopicOwners.TryGetValue(topic, out var owner))
                throw new ManifestError(
                    $"events.publishes '{topic}' is not a registered topic; the platform registers " +
                    "topic ownership (ADR-0019) before a workload may publish to it.");
            if (owner != workload)
                throw new ManifestError(
                    $"events.publishes '{topic}' is owned by {owner}; {workload} may not publish to " +
                    "another owner's topic (ADR-0019).");
        }

        var defaultSubscription = workload.StartsWith("svc-") ? workload[4..] : workload;
        var subscribes = new List<Subscription>();
        foreach (var entry in events["subscribes"] as JsonArray ?? [])
        {
            var sub = entry!["subscription"]?.GetValue<string>();
            var pair = new Subscription(entry["topic"]!.GetValue<string>(), string.IsNullOrEmpty(sub) ? defaultSubscription : sub);
            if (subscribes.Contains(pair))
                throw new ManifestError($"events.subscribes repeats {pair.Topic}/{pair.Name}.");
            subscribes.Add(pair);
        }
        return (publishes, subscribes);
    }

    static string EventsBicep(List<string> publishes, List<Subscription> subscribes, string workload)
    {
        if (publishes.Count == 0 && subscribes.Count == 0) return "";
        var topics = publishes.Concat(subscribes.Select(s => s.Topic)).Distinct().ToList();
        var lines = new List<string>
        {
            "",
            "// queue (ADR-0019): the namespace, its topics and subscriptions are platform-created;",
            "// this composition only references them and grants the workload identity its roles:",
            "// Sender on its own topic only, Receiver only on its own subscriptions.",
            "@description('Existing platform Service Bus namespace (topics and subscriptions are created by the platform, never by this composition).')",
            "param serviceBusNamespace string",
            "",
            "resource serviceBus 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' existing = {",
            "  name: serviceBusNamespace",
            "}",
        };
        foreach (var topic in topics)
            lines.AddRange([
                "",
                $"resource {Symbol(topic)}Topic 'Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview' existing = {{",
                "  parent: serviceBus",
                $"  name: '{topic}'",
                "}",
            ]);
        foreach (var topic in publishes)
        {
            var sym = Symbol(topic);
            lines.AddRange(RoleAssignment($"{sym}Sender", $"{sym}Topic", workload, SbSenderRole));
        }
        foreach (var (topic, subscription) in subscribes)
        {
            var subSym = $"{Symbol(topic)}{Symbol(subscription)}Subscription";
            lines.AddRange([
                "",
                $"resource {subSym} 'Microsoft.ServiceBus/namespaces/topics/subscriptions@2022-10-01-preview' existing = {{",
                $"  parent: {Symbol(topic)}Topic",
                $"  name: '{subscription}'",
                "}",
            ]);
            lines.AddRange(RoleAssignment($"{subSym}Receiver", subSym, workload, SbReceiverRole));
        }
        return string.Join("\n", lines) + "\n";
    }

    static string[] RoleAssignment(string symbol, string scope, string workload, string role) =>
    [
        "",
        $"resource {symbol} 'Microsoft.Authorization/roleAssignments@2022-04-01' = {{",
        $"  name: guid({scope}.id, '{workload}', '{role}')",
        $"  scope: {scope}",
        "  properties: {",
        "    principalId: hosting.outputs.principalId",
        $"    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '{role}')",
        "    principalType: 'ServicePrincipal'",
        "  }",
        "}",
    ];

    // ---- generate ----------------------------------------------------------

    /// <summary>Return main.bicep for a schema-valid manifest.</summary>
    public static string Generate(JsonObject manifest, string? localModuleRef = null)
    {
        var caps = Strings(manifest["capabilities"]);
        var pending = caps.Where(NotYetSupported.Contains).ToList();
        if (pending.Count > 0)
            throw new ManifestError(
                $"capability {string.Join(", ", pending)} is not yet supported: no governed module exists " +
                "(platform-handbook #58). Supported today: http, identity, queue.");
        if (!caps.Contains("http"))
            throw new ManifestError(
                "capabilities must include http: the only module today is container-app-service, " +
                "which hosts an HTTP workload. identity on its own has nothing to attach to.");

        var (publishes, subscribes) = EventsOf(manifest);

        var name = manifest["workload"]!.GetValue<string>();
        if (!AppName.IsMatch(name))
            throw new ManifestError(
                $"workload '{name}' cannot name a container app: use 2-28 lowercase letters, " +
                "numbers or hyphens, starting with a letter.");

        var pin = manifest["modules"]?["hosting"]?.GetValue<string>();
        if (!string.IsNullOrEmpty(pin))
        {
            var match = Pin.Match(pin);
            if (!match.Success || match.Groups[1].Value != HostingModule)
                throw new ManifestError($"modules.hosting '{pin}' is not a {HostingModule} pin; it is the only hosting module.");
        }
        var moduleRef = localModuleRef ?? (string.IsNullOrEmpty(pin)
            ? throw new ManifestError(
                "modules.hosting is not set, and no module is published yet. " +
                "Pin one (for example br/platform:container-app-service:0.1.0) or run with --local-modules.")
            : pin);

        var source = localModuleRef is not null ? "local stand-in, --local-modules" : "registry pin";
        var repo = manifest["repo"]!.GetValue<string>();
        var dataClass = manifest["dataClass"]!.GetValue<string>();
        // Raw string: Bicep braces stay single; {{x}} is interpolation.
        return $$"""
// GENERATED by aeroflow-workflows generator {{GeneratorVersion}} from workload.yaml. Do not edit or commit (ADR-0009).
// workload: {{name}}  repo: {{repo}}  dataClass: {{dataClass}}
// capabilities: {{string.Join(", ", caps)}}
// hosting module: {{HostingModule}} ({{source}})
targetScope = 'resourceGroup'

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Container image for the workload, supplied by the deploy step.')
param containerImage string

@description('HTTP ingress. Internal unless the deploy step asks for external.')
@allowed([
  'external'
  'internal'
])
param ingress string = 'internal'

// http + identity: one container app with a system-assigned managed identity.
module hosting '{{moduleRef}}' = {
  name: '{{name}}-hosting'
  params: {
    name: '{{name}}'
    location: location
    containerImage: containerImage
    ingress: ingress
  }
}

""".ReplaceLineEndings("\n") + EventsBicep(publishes, subscribes, name);
    }

    // ---- CLI ---------------------------------------------------------------

    public static int Run(string[] argv)
    {
        string manifestPath = "workload.yaml";
        string? outDir = null, localModules = null;
        for (var i = 0; i < argv.Length; i++)
        {
            string Next() => i + 1 < argv.Length ? argv[++i] : throw new ArgumentException($"{argv[i]} needs a value");
            try
            {
                switch (argv[i])
                {
                    case "--manifest": manifestPath = Next(); break;
                    case "--out-dir": outDir = Next(); break;
                    case "--local-modules": localModules = Next(); break;
                    case "-h" or "--help":
                        Console.WriteLine("usage: generate.cs [--manifest MANIFEST] --out-dir OUT_DIR [--local-modules LOCAL_MODULES]");
                        return 0;
                    default: throw new ArgumentException($"unrecognized arguments: {argv[i]}");
                }
            }
            catch (ArgumentException ex) { Console.Error.WriteLine($"error: {ex.Message}"); return 2; }
        }
        if (outDir is null) { Console.Error.WriteLine("error: the following arguments are required: --out-dir"); return 2; }

        string bicep;
        try
        {
            var manifest = LoadManifest(manifestPath);
            string? localRef = null;
            if (localModules is not null)
            {
                var target = Path.Combine(localModules, HostingModule, "main.bicep");
                if (!File.Exists(target)) throw new ManifestError($"no local stand-in at {target}");
                localRef = Path.GetRelativePath(Path.GetFullPath(outDir), Path.GetFullPath(target)).Replace('\\', '/');
            }
            bicep = Generate(manifest, localRef);
        }
        catch (ManifestError ex)
        {
            Console.Error.WriteLine($"error: {ex.Message}");
            return 1;
        }

        Directory.CreateDirectory(outDir);
        var output = Path.Combine(outDir, "main.bicep");
        File.WriteAllText(output, bicep, new UTF8Encoding(false));
        Console.WriteLine($"wrote {output}");
        return 0;
    }
}
