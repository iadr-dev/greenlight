namespace Greenlight.Tests.Sample;

/// <summary>Returned when a number is below zero.</summary>
public sealed class NegativeInputException(int value) : Exception("negative input")
{
    public int Value { get; } = value;
}

/// <summary>The code the sample feature tests. Delete it with the sample.</summary>
public static class Calculator
{
    public static int Add(int a, int b)
    {
        if (a < 0)
        {
            throw new NegativeInputException(a);
        }
        if (b < 0)
        {
            throw new NegativeInputException(b);
        }
        return a + b;
    }
}
