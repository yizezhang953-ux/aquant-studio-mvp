from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_MODULE_ROOT = REPO_ROOT

DATA_MODULE = LEGACY_MODULE_ROOT / "data_module"
STRATEGY_MODULE = LEGACY_MODULE_ROOT / "strategy_module"
BACKTEST_MODULE = LEGACY_MODULE_ROOT / "backtest_module"
TEMPLATE_MODULE = LEGACY_MODULE_ROOT / "template_module"
SECURITY_COMPLIANCE_MODULE = LEGACY_MODULE_ROOT / "security_compliance_module"
