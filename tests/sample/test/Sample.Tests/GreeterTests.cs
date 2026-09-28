namespace Sample.Tests;

public class GreeterTests
{
    [Fact]
    public void Greet_includes_the_name()
    {
        Assert.Equal("Hello, AeroFlow", Greeter.Greet("AeroFlow"));
    }
}
