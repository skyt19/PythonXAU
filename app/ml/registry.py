"""Model registry for version control and safe deployment"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import torch

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Manage model versions and safe deployment."""

    def __init__(self, registry_dir: str = "artifacts/registry"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.registry_dir / "registry.json"

        if self.metadata_file.exists():
            with open(self.metadata_file) as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {"models": [], "active_model": None}
            self._save_metadata()

    def register_model(
        self,
        model_path: Path,
        model_type: str,
        metrics: Dict,
        description: str = "",
    ) -> str:
        """Register a trained model."""
        timestamp = datetime.now().isoformat()
        model_id = f"{model_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Copy model to registry
        registry_path = self.registry_dir / f"{model_id}.pt"
        shutil.copy(model_path, registry_path)

        # Save metadata
        model_info = {
            "model_id": model_id,
            "model_type": model_type,
            "registered_at": timestamp,
            "path": str(registry_path),
            "metrics": metrics,
            "description": description,
            "status": "registered",
        }

        self.metadata["models"].append(model_info)
        self._save_metadata()

        logger.info(f"Registered model: {model_id}")
        logger.info(f"Metrics: {metrics}")

        return model_id

    def activate_model(self, model_id: str) -> bool:
        """Activate a model for production use."""
        model_info = self._get_model_info(model_id)
        if not model_info:
            logger.error(f"Model not found: {model_id}")
            return False

        # Deactivate previous
        if self.metadata["active_model"]:
            prev_info = self._get_model_info(self.metadata["active_model"])
            if prev_info:
                prev_info["status"] = "inactive"

        # Activate new
        model_info["status"] = "active"
        self.metadata["active_model"] = model_id
        self._save_metadata()

        logger.info(f"Activated model: {model_id}")
        return True

    def get_active_model(self) -> Optional[Dict]:
        """Get active model info."""
        if not self.metadata["active_model"]:
            return None
        return self._get_model_info(self.metadata["active_model"])

    def list_models(self) -> list:
        """List all registered models."""
        return self.metadata["models"]

    def load_active_model(self, model_class):
        """Load the active model."""
        active_info = self.get_active_model()
        if not active_info:
            raise ValueError("No active model")

        checkpoint = torch.load(active_info["path"], weights_only=True)

        # Reconstruct model (need to get params from somewhere)
        # This is a simplified version - real impl would save model config
        model = model_class()
        model.load_state_dict(checkpoint['model_state'])
        model.eval()

        return model, active_info

    def _get_model_info(self, model_id: str) -> Optional[Dict]:
        """Get model info by ID."""
        for model in self.metadata["models"]:
            if model["model_id"] == model_id:
                return model
        return None

    def _save_metadata(self):
        """Save registry metadata."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
