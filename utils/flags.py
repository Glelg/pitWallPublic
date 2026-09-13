# utils/flags.py

# Международный стандарт ISO 3166-1 (alpha-3 в alpha-2 для иконок флагов)
ISO_ALPHA3_TO_ALPHA2 = {
    "ARG": "ar", "AUS": "au", "AUT": "at", "BEL": "be", "BRA": "br",
    "CAN": "ca", "CHN": "cn", "CZE": "cz", "DEN": "dk", "DNK": "dk",
    "FIN": "fi", "FRA": "fr", "GER": "de", "DEU": "de", "GBR": "gb",
    "HUN": "hu", "IDN": "id", "IND": "in", "ISR": "il", "ITA": "it",
    "JPN": "jp", "MEX": "mx", "MON": "mc", "NED": "nl", "NLD": "nl",
    "NZL": "nz", "POL": "pl", "PRT": "pt", "RUS": "ru", "ESP": "es",
    "SWE": "se", "CHE": "ch", "SUI": "ch", "THA": "th", "USA": "us", "ZAF": "za",
    "BHR": "bh", "QAT": "qa", "ARE": "ae", "SAU": "sa", "SGP": "sg", "MYS": "my"
}

def get_country_flag(country_code_str: str) -> str:
    """Конвертирует 3-буквенный ISO код страны от OpenF1 в 2-буквенный для иконок флагов"""
    if not country_code_str:
        return ""
    code = country_code_str.upper().strip()
    return ISO_ALPHA3_TO_ALPHA2.get(code, code.lower()[:2])