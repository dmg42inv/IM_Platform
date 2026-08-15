from pathlib import Path

REPORTING_CURRENCY = "USD"

REQUIRED_FILES = {
    "investment_register": "Investment_Register",
    "cashflow": "Transaction_Cash_Flow",
    "valuation": "Valuation_Marks",
    "monitoring": "Monthly_Monitoring",
    "decisions": "Governance_Decisions",
}

OUTPUT_FILE_NAME = "V1_Portfolio_Output.xlsx"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT_ROOT = PROJECT_ROOT / "data" / "inputs"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "outputs"
