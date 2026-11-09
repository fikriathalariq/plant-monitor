# 🏭 Plant Monitor — Industrial IoT, Energy Analytics & Physics-Informed Neural Network (PINN) Platform

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Django 5.x](https://img.shields.io/badge/django-5.x-green.svg)](https://www.djangoproject.com/)
[![Django Ninja](https://img.shields.io/badge/django--ninja-REST%20OpenAPI-teal.svg)](https://django-ninja.dev/)
[![React 18](https://img.shields.io/badge/react-18-61dafb.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/vite-8.0-646cff.svg)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/tailwind-3.4-38bdf8.svg)](https://tailwindcss.com/)
[![PostgreSQL 17](https://img.shields.io/badge/postgresql-17-336791.svg)](https://www.postgresql.org/)
[![Physics-Informed ML](https://img.shields.io/badge/AI%2FML-PINN%20Engine-ff69b4.svg)](docs/PINN_ENGINE_SPECIFICATION.md)
[![DevOps](https://img.shields.io/badge/DevOps-Blue--Green%20Deployment-orange.svg)](docs/BLUE_GREEN_ARCHITECTURE.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-76%2F76%20Passing%20(100%25)-brightgreen.svg)](#-running-automated-tests--qa-suite)
[![CI Pipeline](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-success.svg)](.github/workflows/ci.yml)

---

## 📌 Executive Summary

**Plant Monitor** is an enterprise-grade **Industrial IoT (IIoT), Energy Telemetry, and Physics-Informed Machine Learning** platform deployed in continuous textile manufacturing facilities (dyeing and stenter finishing). 

The platform bridges real-world factory floor controllers (JUMO Modbus/TCP, steam mass flowmeters, high-voltage power meters) with high-performance modern web software. It continuously tracks thermal dynamics, predicts steam mass consumption via **Physics-Informed Neural Networks (PINN)** conforming to thermodynamic principles, detects operational anomalies in real time, and automates multi-machine batch cost attribution.

```mermaid
flowchart TB
    subgraph Floor["🏭 Factory Floor & Telemetry Acquisition"]
        JUMO["JUMO Process Controllers\n(Modbus/TCP)"]
        SteamSensors["Steam Flow & Pressure\n(Telemetry)"]
        PowerSensors["Electricity & Power\n(Modbus Analyzers)"]
    end

    subgraph Ingestion["⚡ Real-Time Ingestion & Daemons"]
        RealtimeWorker["JUMO Realtime Daemon\n(Sub-second Polling)"]
        HistoryLogger["Minute History Logger\n(Aggregations & Metrics)"]
        AnomalyDaemon["Anomaly Detection Worker\n(Statistical & Rule Checks)"]
        Supervisor["Singleton Process Supervisor\n(PowerShell Guard)"]
    end

    subgraph Storage["💾 Persistence & Cache Layer"]
        Postgres[("PostgreSQL 17\nPartitioned & Indexed")]
        RedisCache[("Redis / Memory Cache\nTelemetry Cache")]
    end

    subgraph Core["🧠 Analytics, AI & API Engine"]
        DjangoNinja["Django Ninja REST API\n(Async OpenAPI / Swagger)"]
        PINNEngine["PINN Steam Predictor\n(Thermodynamic Loss / MLP)"]
        CostAttribution["Batch Cost & Tariff Engine\n(Electric & Thermal Breakdown)"]
    end

    subgraph Gateway["🛡️ Gateway & High Availability"]
        Nginx["Nginx Reverse Proxy\n(Port 8000 Gateway)"]
        WaitressBlue["Waitress WSGI Slot Blue\n(Port 8081)"]
        WaitressGreen["Waitress WSGI Slot Green\n(Port 8082)"]
        Watchdog["Autonomous Watchdog\n(Auto-Healing / Self-Recovery)"]
    end

    subgraph Presentation["🖥️ User Interface & Notifications"]
        ReactApp["React 18 SPA (Vite)\n(Dashboard, Charts, Telemetry)"]
        TelegramBot["Telegram Notification Bot\n(Critical Downtime Alerts)"]
    end

    Floor --> RealtimeWorker
    Floor --> HistoryLogger
    Floor --> PowerSensors
    Supervisor --> RealtimeWorker
    Supervisor --> HistoryLogger
    Supervisor --> AnomalyDaemon

    RealtimeWorker --> Postgres
    HistoryLogger --> Postgres
    HistoryLogger --> RedisCache

    Postgres --> DjangoNinja
    RedisCache --> DjangoNinja
    PINNEngine <--> DjangoNinja
    CostAttribution <--> DjangoNinja

    Nginx --> WaitressBlue
    Nginx --> WaitressGreen
    WaitressBlue --> DjangoNinja
    WaitressGreen --> DjangoNinja
    Watchdog -.->|Healthcheck & Auto-Heal| Nginx
    Watchdog -.->|Healthcheck & Auto-Heal| WaitressBlue
    Watchdog -.->|Healthcheck & Auto-Heal| Supervisor

    DjangoNinja --> ReactApp
    AnomalyDaemon --> TelegramBot
```

---

## 🌟 Key Technical Highlights

### 1. Physics-Informed Neural Network (PINN) Engine
Unlike standard black-box regressors that can yield non-physical outputs (such as negative steam consumption during machine idle states), our **PINN Steam Engine** (`monitoring/services/pinn_engine.py`) embeds physical boundary conditions into its loss and inference formulation:
- **Energy Conservation Formulation:**
  $$\dot{Q} = \dot{m}_{\text{steam}} \cdot \Delta h_{\text{vap}} = m_{\text{fabric}} \cdot c_p \cdot \frac{dT}{dt} + U \cdot A \cdot (T - T_{\infty})$$
- **3-Layer Physics Model:** Incorporates water thermal mass, fabric sensible heat, and ambient convective dissipation.
- **Thermodynamic Safety Boundary:** Restricts mass-rate deviations and enforces zero/minimal steam draw when bath temperature is equal to or below ambient ambient gradients.
- **Dynamic Weight Optimization:** Automatically balances empirical MSE loss with differential physical residual loss.

### 2. High-Throughput Industrial Ingestion & Singleton Supervisor
- **Sub-Second Polling:** Dedicated Modbus/TCP client daemons poll industrial PLC registers continuously without blocking the web application.
- **Aggregated History Pipeline:** Minute-level historical aggregation buffers compute Rolling Mean, Max Peak, and Thermal Deviation indices on the fly.
- **Singleton Process Supervisor (`scripts/start_background_workers.ps1`):** Monitors 6 background daemons via CIM/WMI process filtering, preventing duplicate telemetry pollers and avoiding race conditions on Telegram webhook listeners.

### 3. Enterprise Blue-Green Deployment & Self-Healing Watchdog
- **Zero-Downtime Deployment (`deploy.ps1`):** 
  - Runs in a Blue/Green architecture on ports `8081` (Blue) and `8082` (Green).
  - Prepares the idle slot, preloads WSGI application modules, verifies warm-up health at `/api/v1/health`, flips Nginx upstream via atomic configuration reload, and gracefully shuts down the inactive slot.
  - Automatically triggers `rollback.ps1` in case of failed health checks.
- **Autonomous Watchdog (`watchdog_heal.ps1`):** 
  - Periodic supervisor inspecting PostgreSQL, Nginx, active Waitress slot latency, and background worker status.
  - Features self-healing recovery actions (spawns missing daemons, restarts dead slots, reloads Nginx routing automatically).

### 4. High-Performance API & Typed Contracts
- **Django Ninja REST API:** Built with type annotations and Pydantic schemas, providing schema-validated serializations and interactive Swagger/OpenAPI documentation at `/api/v1/docs`.
- **Database Partitioning & Coverage Indexing:** BRIN and composite B-Tree indexes on multi-million row minute-log tables (`MachineMinuteLog`, `MachineStatusSnapshot`) deliver sub-50ms dashboard response times even across multi-month historical queries.

### 5. Modern Reactive Frontend
- **React 18 + Vite:** Fast Single-Page Application utilizing Lucide icons, Recharts high-density time-series plots, and Tailwind CSS.
- **Deep Machine Analytics:** Interactive multi-sensor overlays (temperature profile, speed, steam pressure, current draw), historical batch playback, and downtime classification.

---

## 📂 Repository Structure

The codebase is organized following clean architectural boundaries and separation of concerns:

```
plant-monitor/
├── monitoring/                   # Core Django Application
│   ├── api.py                    # Django Ninja API Root Router
│   ├── api_analytics.py          # Real-time Telemetry & Time-series API
│   ├── api_report.py             # Shift & Daily Production Summary API
│   ├── models.py                 # Core Relational & Industrial Telemetry Models
│   ├── models_production_reports.py # Finishing & Stenter Production Models
│   ├── services/                 # Pure Business Logic & ML Engines
│   │   ├── pinn_engine.py        # Physics-Informed Neural Network Steam Predictor
│   │   └── ...                   # Anomaly Detection & Tariff Calculators
│   ├── tests/                    # Enterprise 6-Layer Automated Test Suites
│   │   ├── test_pinn_engine.py
│   │   ├── test_electricity_metrics.py
│   │   ├── test_admin_and_routes.py
│   │   ├── test_root_entrypoints.py
│   │   ├── test_batch_analyzer.py
│   │   ├── test_modbus_and_telemetry.py
│   │   ├── test_steam_and_shift_calc.py
│   │   ├── test_production_reports.py
│   │   ├── test_security_and_rbac.py
│   │   └── test_ninja_api.py
│   └── templates/                # Django Admin Custom Templates
├── plant_monitor/                # Django Project Configuration (settings, urls, wsgi)
├── frontend/                     # Modern React 18 + Vite SPA
│   ├── src/
│   │   ├── pages/                # Dashboard, Machine Analytics, Reports
│   │   ├── components/           # Industrial Charts, Modals, Navigation
│   │   ├── lib/__tests__/        # Node.js Client-Side Unit Tests
│   │   └── services/             # Axios / Fetch API Clients
│   └── package.json
├── scripts/                      # Operational & Diagnostic Tooling
│   ├── ops/                      # Operational Scripts (run_all_tests, loop_anomalies)
│   ├── diagnostics/              # Telemetry & DB Analysis Scripts (128 tools)
│   ├── reports/                  # Automated HTML/CSV Generators & Plotters
│   ├── patches/                  # Data Migration & Backfill Utilities
│   ├── legacy_tests/             # Manual Integration & Diagnostic Scripts
│   ├── seeders/                  # Flow & Master Fabric Seed Scripts
│   └── start_background_workers.ps1 # Singleton Worker Supervisor
├── docs/                         # Engineering Plans & Scientific Specifications
│   ├── PINN_ENGINE_SPECIFICATION.md # Thermodynamic & Neural Network Spec
│   ├── BLUE_GREEN_ARCHITECTURE.md   # High Availability & Watchdog Spec
│   ├── IMPLEMENTATION_PLAN_FASE_3_TESTING_QA.md
│   └── legacy_notes/             # Historical Architecture & Planning Records
├── archive/                      # Archived Legacy Dumps & Deprecated Assets
├── logs/                         # Runtime Logs (bot_requests, auto_heal, perf)
├── deploy.ps1                    # Production Zero-Downtime Blue-Green Deployer
├── rollback.ps1                  # Automated Rollback Script
├── watchdog_heal.ps1             # Autonomous Self-Healing Watchdog
├── run_server.py                 # Production Waitress WSGI Server Entrypoint
├── manage.py                     # Django Management CLI
├── Dockerfile                    # Containerization Specification
├── docker-compose.yml            # Multi-Container Compose Configuration
├── requirements.txt              # Pinned Python Dependencies
└── LICENSE                       # MIT Open Source License
```

---

## 🚀 Quick-Start Guide

### Prerequisites
- **Python 3.12+** with `pip` and virtual environment support
- **Node.js 18+** and `npm`
- **PostgreSQL 16+** (PostgreSQL 17 recommended)
- **Nginx** (optional for local dev, required for Blue-Green production routing)

---

### Local Development Setup

#### 1. Clone the Repository
```bash
git clone https://github.com/your-username/plant-monitor.git
cd plant-monitor
```

#### 2. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Edit `.env` with your PostgreSQL database credentials and secret key:
```ini
DEBUG=True
SECRET_KEY=your-secure-development-secret-key
DATABASE_URL=postgres://postgres:password@localhost:5432/plantmonitor
ALLOWED_HOSTS=localhost,127.0.0.1
```

#### 3. Backend Setup & Virtual Environment
```bash
# Create and activate virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create an administrator account
python manage.py createsuperuser
```

#### 4. Frontend Setup
```bash
cd frontend
npm install
npm run build
cd ..
```

#### 5. Launch the Development Server
```bash
# Start Django development server
python manage.py runserver 0.0.0.0:8000
```
- Web Application: `http://localhost:8000`
- Interactive API Swagger: `http://localhost:8000/api/v1/docs`
- Django Administration: `http://localhost:8000/admin`

---

## 🐳 Docker Deployment

The system is fully containerized with Docker and Docker Compose:

```bash
# Build and start all services (Web, PostgreSQL, Nginx, Workers)
docker compose up -d --build

# View container logs
docker compose logs -f

# Teardown
docker compose down
```

---

## 🧪 Running Automated Tests & QA Suite

Plant Monitor features an **Enterprise 6-Layer Automated Testing Pyramid** spanning backend thermodynamics, machine telemetry decoders, security filters, OpenAPI contracts, and frontend reactive planning geometry:

### Single Command Unified Test Runner
Runs Backend Unit Tests, Statement Coverage, Frontend Unit Tests, and Production Build in one automated pipeline:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\ops\run_all_tests.ps1
```

### 1. Backend Django & Ninja Unit Tests (65 Tests, 100% Mocked / In-Memory)
```bash
python -m coverage run --rcfile=.coveragerc manage.py test `
    monitoring.tests.test_pinn_engine `
    monitoring.tests.test_electricity_metrics `
    monitoring.tests.test_admin_and_routes `
    monitoring.tests.test_root_entrypoints `
    monitoring.tests.test_batch_analyzer `
    monitoring.tests.test_modbus_and_telemetry `
    monitoring.tests.test_steam_and_shift_calc `
    monitoring.tests.test_production_reports `
    monitoring.tests.test_security_and_rbac `
    monitoring.tests.test_ninja_api

# View Statement Coverage
coverage report --rcfile=.coveragerc
```

### 2. Frontend React Unit Tests (11 Tests, Native Node.js Test Runner)
```bash
cd frontend
npm test
```

### Test Suite Highlights
- **PINN Engine & Thermodynamics**: Verifies physics-informed loss function, IAPWS-97 saturation pressure vs. empirical curve fallback, and gradient descent convergence.
- **Hardware Telemetry & Modbus**: IEEE-754 Big-Endian / Little-Endian float decoding, high/low register word order, sensor noise clamping, signal freshness timeout detection, and JUMO controller state machine parity.
- **Shift Rollover & Production**: 06:00 AM shift turnover boundaries, midnight crossings (23:00 to 07:00), 1,440-minute steam timeline rasterizer, downtime event collision resolution, and proportional counter splitting.
- **Security, RBAC & WAF**: IP extraction behind reverse proxies (X-Forwarded-For), BotBlocker malicious scanner protection (WP-Admin, PHPUnit, .env exploits), and operator role-based page guards.
- **Django Ninja REST API**: OpenAPI schema validation across all 18 sub-routers, cache flush security, health probes (HTTP 200 vs 503 degraded), and auth session endpoints.
- **Frontend Planning Geometry**: 06:00-based shift timeline pixel-to-minute transforms, collision detection, and automated stage duration splitting.

---

## 🛡️ DevOps & Production Operations

### Zero-Downtime Blue-Green Deployment
Production deployments are orchestrated via PowerShell automation:
```powershell
# Deploy the latest code to the inactive slot and atomically switch traffic
.\deploy.ps1

# Rollback to the previous slot if necessary
.\rollback.ps1
```

### Starting the Autonomous Watchdog
```powershell
# Start self-healing supervisor in background
powershell.exe -ExecutionPolicy Bypass -File .\watchdog_heal.ps1
```

---

## 📊 Tech Stack Summary

| Layer | Technologies |
| :--- | :--- |
| **Backend & API** | Python 3.12, Django 5.x, Django Ninja (REST / OpenAPI), Waitress WSGI |
| **Machine Learning & Physics** | NumPy, SciPy, Scikit-learn, Physics-Informed Neural Network (PINN) |
| **Industrial Telemetry** | PyModbus, Modbus/TCP, Socket-based PLC Telemetry Streaming |
| **Database & Cache** | PostgreSQL 17 (BRIN & B-Tree indexed), Redis Cache |
| **Frontend UI/UX** | React 18, Vite, Tailwind CSS, Recharts, Lucide Icons |
| **Infrastructure & DevOps** | Nginx, Docker, Docker Compose, PowerShell Blue-Green CI/CD, Autonomous Watchdog |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
