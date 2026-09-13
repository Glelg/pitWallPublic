# utils/flags.py

# Международный стандарт ISO 3166-1 (alpha-3 в alpha-2 для иконок флагов)
ISO_ALPHA3_TO_ALPHA2 = {
    # Специфичные коды стран Формулы-1
    "BRN": "bh", "BHR": "bh",  # Бахрейн (не бразилия!)
    "SAU": "sa", "KSA": "sa",  # Саудовская Аравия
    "ARE": "ae", "UAE": "ae",  # ОАЭ / Абу-Даби
    "QAT": "qa",              # Катар
    "AZE": "az",              # Азербайджан
    "SGP": "sg", "SIN": "sg",  # Сингапур
    "MYS": "my", "MAS": "my",  # Малайзия
    "MCO": "mc", "MON": "mc",  # Монако
    "DEU": "de", "GER": "de",  # Германия
    "NLD": "nl", "NED": "nl",  # Нидерланды

    # Стандартные ISO коды
    "ARG": "ar", "AUS": "au", "AUT": "at", "BEL": "be", "BRA": "br",
    "CAN": "ca", "CHN": "cn", "CZE": "cz", "DEN": "dk", "DNK": "dk",
    "FIN": "fi", "FRA": "fr", "GBR": "gb", "HUN": "hu", "IDN": "id",
    "IND": "in", "ISR": "il", "ITA": "it", "JPN": "jp", "MEX": "mx",
    "NZL": "nz", "POL": "pl", "PRT": "pt", "RUS": "ru", "ESP": "es",
    "SWE": "se", "CHE": "ch", "SUI": "ch", "THA": "th", "USA": "us", "ZAF": "za"
}

def get_country_flag(country_code_str: str) -> str:
    """Конвертирует 3-буквенный ISO код страны от OpenF1 в 2-буквенный для иконок флагов"""
    if not country_code_str:
        return ""
    code = country_code_str.upper().strip()
    return ISO_ALPHA3_TO_ALPHA2.get(code, code.lower()[:2])