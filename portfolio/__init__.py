"""Institutional portfolio construction and allocation engine."""



from portfolio.currency_strength_engine import CurrencyStrengthEngine
from portfolio.exposure_engine import ExposureEngine
from portfolio.portfolio_construction import PortfolioConstructionEngine



PORTFOLIO_DNA_STATEMENT = """

If Kraitos identifies a valid opportunity, Portfolio Management classifies and allocates rather than denies.



The role of Portfolio is not to decide whether opportunity exists.



The role of Portfolio is to determine how much capital should be deployed according to opportunity strength and account conditions.



The default response to opportunity is not 'No.'



The default response is:



'How much?'

""".strip()



__all__ = [
    "CurrencyStrengthEngine",
    "ExposureEngine",
    "PORTFOLIO_DNA_STATEMENT",
    "PortfolioConstructionEngine",
]


