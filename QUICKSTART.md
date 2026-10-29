# XAUUSD AI Farming HQ - Quick Start Guide

## ✅ Phase 1 Complete - Application is Runnable

### Starting the Application

```bash
# From project root
python -m app.main
```

Expected output:
```
INFO - XAUUSD AI Farming HQ - Starting
INFO - Database initialized successfully
INFO - Farming HQ Ready
INFO - Dashboard: http://127.0.0.1:3831
INFO - Execution: DISABLED (no execution module loaded)
INFO - Uvicorn running on http://127.0.0.1:3831
```

### Testing the Endpoints

```bash
# Health check
curl http://localhost:3831/health

# Full status
curl http://localhost:3831/status

# System information
curl http://localhost:3831/api/v1/info

# Configuration
curl http://localhost:3831/api/v1/config

# Statistics
curl http://localhost:3831/api/v1/statistics
```

### Running Tests

```bash
# All tests
PYTHONPATH=/c/z pytest tests/ -v

# Integration tests only
PYTHONPATH=/c/z pytest tests/integration/ -v

# Safety tests only  
PYTHONPATH=/c/z pytest tests/safety/ -v
```

### API Documentation

When the application is running:
- **Swagger UI**: http://localhost:3831/docs
- **ReDoc**: http://localhost:3831/redoc

### Project Structure

```
app/
├── main.py                  # ✅ Application entry point
├── config.py                # ✅ Configuration management
├── database.py              # ✅ Database models
├── logging_config.py        # ✅ Logging setup
├── broker/
│   ├── account_guard.py     # ✅ Demo account verification
│   ├── mt5_client.py        # ✅ MT5 connection
│   └── symbol_specs.py      # ✅ Instrument specs
├── dashboard/
│   ├── api.py               # ✅ API routes
│   └── schemas.py           # ✅ Pydantic models
├── data/
│   └── validator.py         # ✅ Data validation
└── features/
    └── indicators.py        # ✅ Technical indicators
```

### Safety Status

- ✅ DEMO_ONLY enforced
- ✅ Localhost binding only
- ✅ Execution DISABLED
- ✅ No order submission
- ✅ All safety tests passing

### What's NOT Implemented (By Design)

Phase 1 excludes:
- MT5 connection (Phase 2)
- Data collection (Phase 2)
- LSTM model (Phase 3)
- Strategy rules (Phase 3)
- Risk management (Phase 3)
- Order execution (Phase 4)
- Frontend pages (Phase 4)

### Next Steps

See `docs/PROGRESS.md` for Phase 2 roadmap:
- MT5 Integration
- Data Collection
- Historical XAUUSD M15 data

### Documentation

- `README.md` - Complete project overview
- `docs/PROGRESS.md` - Phase 1 progress report (14KB)
- `docs/ARCHITECTURE.md` - System architecture
- `PHASE1_SUMMARY.txt` - Phase 1 completion report
- `PROJECT_STATUS.md` - Implementation tracker
- `IMPLEMENTATION_GUIDE.md` - Development guide

### Support

For issues:
1. Check logs in `logs/farming_hq.log`
2. Review `docs/PROGRESS.md` for known limitations
3. Run tests to verify installation

### Version

- **Application**: v1.0.0
- **Phase**: Phase 1 (Complete)
- **Status**: Runnable, Tested, Safe
- **Last Updated**: 2026-10-29
