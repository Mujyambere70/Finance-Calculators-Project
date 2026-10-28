# Import math module
import math

# Display menu to the user
print("investment - to calculate the amount of interest you'll earn on your investment")
print("bond - to calculate the amount you'll have to pay on a home loan")

# Prompt user for choice
calculation_type = input("Enter either 'investment' or 'bond' from the menu above to proceed: ").lower()

# Validate user input
if calculation_type not in ['investment', 'bond']:
    print("Invalid input. Please enter either 'investment' or 'bond'.")
else:
    if calculation_type == 'investment':
        # Get user input for investment calculation
        principal = float(input("Enter the amount of money you are depositing: "))
        rate = float(input("Enter the interest rate (as a percentage): ")) / 100
        time = int(input("Enter the number of years you plan on investing: "))
        interest_type = input("Enter 'simple' or 'compound' interest: ").lower()

        # Calculate interest based on user input
        if interest_type == 'simple':
            amount_simple = principal * (1 + rate * time)
            print(f"The total amount after {time} years with simple interest is: {amount_simple:.2f}")
        elif interest_type == 'compound':
            amount_compound = principal * math.pow((1 + rate), time)
            print(f"The total amount after {time} years with compound interest is: {amount_compound:.2f}")
        else:
            print("Invalid interest type. Please enter 'simple' or 'compound'.")
    else:  # calculation_type is 'bond'
        # Get user input for bond calculation
        present_value = float(input("Enter the present value of the house: "))
        annual_interest_rate = float(input("Enter the annual interest rate: ")) / 100
        months = int(input("Enter the number of months for bond repayment: "))

        # Calculate monthly repayment
        monthly_interest_rate = annual_interest_rate / 12
        repayment = (monthly_interest_rate * present_value) / (1 - math.pow(1 + monthly_interest_rate, -months))

        print(f"The monthly bond repayment is: {repayment:.2f}")
