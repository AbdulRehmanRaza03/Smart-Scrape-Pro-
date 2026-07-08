"""
Simple FastAPI launcher - skips heavy async initialization
"""
import os
import sys

# Set simple config
os.environ['DEBUG'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///./database/smartscrape.db'

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
