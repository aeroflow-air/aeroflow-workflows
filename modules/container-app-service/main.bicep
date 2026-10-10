// LOCAL STAND-IN for br/platform:container-app-service (ADR-0009, platform-handbook #58).
// Verbatim copy of aeroflow-air/infra-platform modules/container-app-service/main.bicep
// at commit 5097465. That module is not published to any registry yet, and
// publishing to Azure Container Registry is out of scope (zero cost), so the
// generator's --local-modules mode points here so `bicep build` can compile
// the generated composition in CI. Delete this folder once a registry pin
// exists. Do not change it here: change infra-platform and re-copy.
targetScope = 'resourceGroup'

@description('Name of the container app. Lowercase letters, numbers and hyphens, 2 to 28 characters, starting with a letter. The environment is named <name>-env and the log workspace <name>-logs.')
@minLength(2)
@maxLength(28)
param name string

@description('Azure region for the container app, its environment and its log workspace.')
param location string

@description('Container image reference for the HTTP workload.')
param containerImage string

@description('HTTP ingress. external is reachable on the internet; internal stays inside the environment.')
@allowed([
  'external'
  'internal'
])
param ingress string

var moduleName = 'container-app-service'
var moduleVersion = '0.1.0'
var tags = {
  'aeroflow-module': '${moduleName}:${moduleVersion}'
}

var environmentName = '${name}-env'
var workspaceName = '${name}-logs'
var targetPort = 8080

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: ingress == 'external'
        targetPort: targetPort
        transport: 'http'
      }
    }
    template: {
      containers: [
        {
          name: name
          image: containerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
      }
    }
  }
}
