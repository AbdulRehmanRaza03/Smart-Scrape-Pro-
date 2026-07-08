"""
SmartScrape Pro — Logging Configuration
Standard logging fallback (loguru compatible interface)
"""
import sys
import os
import logging

# Create a simple logger that mimics loguru interface
class LoggerAdapter:
    def __init__(self):
        self.logger = logging.getLogger("smartscrape")
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)
    
    def debug(self, msg):
        self.logger.debug(msg)
    
    def info(self, msg):
        self.logger.info(msg)
    
    def success(self, msg):
        self.logger.info("✅ " + msg)
    
    def warning(self, msg):
        self.logger.warning(msg)
    
    def error(self, msg):
        self.logger.error(msg)
    
    def critical(self, msg):
        self.logger.critical(msg)

logger = LoggerAdapter()

def setup_logging():
    """Configure logging for production-ready output."""
    os.makedirs("./logs", exist_ok=True)
    logger.info("📝 Logging configured")
