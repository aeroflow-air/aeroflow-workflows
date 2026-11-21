using AeroFlow.ServiceDefaults;

namespace Sample.Packages.Tests;

public class PackageRestoreTests
{
    [Fact]
    public void ServiceDefaults_package_is_restored()
    {
        Assert.Equal(10_000, PlatformEventIds.BusinessEventsStart);
    }
}
