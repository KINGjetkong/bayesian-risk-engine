import requests
import os
import logging

logger = logging.getLogger("TradeOddsClient")

class TradeOddsClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TRADEODDS_API_KEY")
        self.base_url = "https://tradeodds-production.up.railway.app"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def get_market_prior(self, symbol: str = "SPY"):
        """
        Queries TradeOdds for the historical win rate of the current pattern.
        This serves as the Bayesian 'Prior' for the 0DTE trade.
        """
        if not self.api_key:
            logger.warning("No TRADEODDS_API_KEY found. Using fallback base rate.")
            return None

        url = f"{self.base_url}/api/v1/analyze"
        
        # Default analysis payload for pre-market prior
        # Looking for similar historical scenarios based on recent price action
        payload = {
            "symbol": symbol,
            "conditions": {
                "daily_change": {"operator": "between", "value": [-0.01, 0.01]},
                "rsi": {"operator": "between", "value": [30, 70]}
            }
        }

        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract the 1D forward win rate as our prior probability
            # Expected structure: {"results": {"forward_returns": {"1d": {"win_rate": 0.54}}}}
            win_rate = data.get("results", {}).get("forward_returns", {}).get("1d", {}).get("win_rate")
            
            if win_rate is not None:
                logger.info(f"TradeOdds Prior for {symbol}: {win_rate:.2%}")
                return win_rate
            
            return None
        except Exception as e:
            logger.error(f"TradeOdds API Error: {e}")
            return None

if __name__ == "__main__":
    # Test call
    client = TradeOddsClient("sk-to-5a4055...") # Use partial or env
    print(client.get_market_prior("SPY"))
