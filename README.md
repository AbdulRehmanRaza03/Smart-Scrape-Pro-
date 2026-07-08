<div align="center">
  <h1>🕷️ SmartScrape Pro</h1>
  <p><b>Enterprise-Grade Web Scraping SaaS Platform</b></p>

  [![Python](https://img.shields.io/badge/Python-3.14+-blue.svg?logo=python&logoColor=white)](#)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0+-00a393.svg?logo=fastapi&logoColor=white)](#)
  [![Playwright](https://img.shields.io/badge/Playwright-Enabled-45ba4b.svg?logo=playwright&logoColor=white)](#)
  [![Celery](https://img.shields.io/badge/Celery-Distributed-37814A.svg?logo=celery&logoColor=white)](#)
  [![Stripe](https://img.shields.io/badge/Stripe-Integrated-008CDD.svg?logo=stripe&logoColor=white)](#)
</div>

---

## 🌟 Overview

**SmartScrape Pro** is a comprehensive, production-ready SaaS platform built for automated and large-scale web scraping. It allows users to extract data from virtually any website using intelligent auto-fallback engines (Playwright for dynamic SPAs -> BeautifulSoup for static HTML).

Complete with a beautiful User Dashboard for job management, a powerful Admin Control Panel, Multi-tier Subscription Plans, and Asynchronous Distributed Task Processing via Celery.

---

## ✨ Key Features

*   🚀 **Intelligent Scraping Engine**: Automatically selects the best engine (Playwright / BeautifulSoup4) to defeat anti-bot measures and handle JavaScript-heavy sites.
*   🏢 **Multi-Tenant SaaS**: Full role-based access control (RBAC). Isolate user data flawlessly.
*   💳 **Flexible Payments**: Global support via Stripe subscriptions + Regional Manual Payments (Easypaisa, JazzCash, Bank Transfers) with an admin review pipeline.
*   ⚙️ **Distributed Background Jobs**: Engineered with Celery & Redis to handle thousands of concurrent scraping tasks without blocking the web server.
*   📊 **Rich Dashboards**: 
    *   **User Panel**: Track job statuses, download extracted data (CSV, JSON, XLSX), manage profile and API keys.
    *   **Admin Panel**: Global statistics, user management, manual payment approvals, and broadcast notifications.
*   🔒 **High Security**: Uses strong Argon2 password hashing, JWT token-based auth, and rigorous API rate-limiting.

---

## 🛠️ Technology Stack

| Category | Technologies |
| :--- | :--- |
| **Backend Framework** | FastAPI, Python 3.14+, Pydantic |
| **Database & ORM** | SQLAlchemy 2.0 (Async), SQLite (Dev) / PostgreSQL (Prod) |
| **Auth & Security** | Python-JOSE (JWT), Argon2-cffi, SlowAPI (Rate Limiting) |
| **Scraping Engines** | Playwright (Headless Chromium), BeautifulSoup4, lxml |
| **Task Queue** | Celery, Redis |
| **Frontend UI** | HTML5, Native CSS3 (Dark Theme), Vanilla JS (Zero Build Step) |

---

## 📂 Project Architecture

```text
SmartScrapePro/
├── backend/
│   ├── auth/           # JWT security, argon2 hashing, RBAC dependencies
│   ├── models/         # SQLAlchemy Async ORM definitions
│   ├── routes/         # REST API endpoints (users, jobs, admin, payments)
│   ├── scraping/       # Scraper engine logic and proxies
│   ├── scheduler/      # Celery task definitions for background workers
│   └── utils/          # Custom Logger wrapper, middleware setup
├── frontend/
│   └── templates/      # Jinja/Static HTML views (auth, admin, dashboard)
├── database/           # SQLite DB file and environment migrations
├── config/             # Environment configs (settings.py, .env)
├── exports/            # Auto-generated CSV/JSON/XLSX user downloads
├── run.py              # Application CLI Runner
└── main.py             # FastAPI App Entry Point
```

---

## ⚡ Getting Started (Local Development)

### 1. Prerequisites
Ensure you have the following installed:
*   **Python 3.14+**
*   **Redis** (If using Celery for background jobs. Otherwise, background tasks run locally)
*   **Git**

### 2. Installation
Clone the repository and jump into the directory:
```bash
git clone https://github.com/your-org/smartscrape-pro.git
cd SmartScrapePro
```

Install application dependencies:
```bash
pip install -r requirements.txt
```

**Crucial Step:** Install Playwright's Headless Browsers & parsers:
```bash
pip install lxml
playwright install chromium
```

### 3. Environment Configuration
Copy the sample environment file:
```bash
cp config/.env.example config/.env
```
Ensure you have the following keys in your `.env` file minimum:
```env
APP_SECRET_KEY="super-secret-key"
JWT_SECRET_KEY="jwt-super-secure-key"
ADMIN_EMAIL="admin@smartscrapepro.com"
ADMIN_PASSWORD="AdminPass123!"
```

### 4. Database Setup
Initialize the database schemas and generate the master admin account:
```bash
python init_db.py
```

### 5. Launch the Platform
Start the FastAPI server:
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Next, open up a *second* terminal and spin up the Celery worker for heavy scraping task background queueing:
```bash
celery -A backend.scheduler.tasks worker --loglevel=info
```

---

## 🌐 Platform Navigation & Usage

Once your server is running, use these direct links:
*   **User Interface**: [http://localhost:8000/auth/login](http://localhost:8000/auth/login)
*   **User Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
*   **Admin Dashboard**: [http://localhost:8000/admin](http://localhost:8000/admin)
*   **Interactive API Docs**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs) *(Powered by Swagger UI)*

### Creating Your First Scrape Job
1. Log in.
2. Click **New Job** from the dashboard.
3. Input your **Target URL**, Map your **CSS Selectors** using JSON format `{"title": "h1.product-title"}`, specify download format natively.
4. Hit **Create & Run**. Once the background task marks as `Completed`, hit the **Download** button.

---

## 💳 Core Ecosystem: Subscriptions & Auth

SmartScrape uses robust token validations to manage subscription rules automatically:

| Plan | Base Rate | Concurrent Jobs | API Access | Features included |
| :--- | :--- | :--- | :--- | :--- |
| **Free** | $0/mo | 1 | ❌ | Basic Scrape (3 jobs limit) |
| **Basic** | $10/mo | 2 | ❌ | Playwright Enabled (10 jobs) |
| **Pro**| $30/mo | 5 | ❌ | Scheduling, Ext Exports (100) |
| **Business**| $100/mo | 20 | ✅ | Unlimited Jobs + API Access |

---

## 🛡️ License & Contributing

Distributed under the **MIT License**. See `LICENSE` for more information. 

> *For enterprise support or bug reporting, please use the GitHub Issues page.*
