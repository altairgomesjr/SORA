import json
from importlib import resources
from pathlib import Path

import requests
import logging

from tqdm import tqdm

from sora.config.core import Config

config = Config()


class PlanetaryKernelDB:
    def __init__(self):
        self.metadata_path = config.data_path / config.ephem.planet_kernels
        self.download_dir = config.data_path / config.ephem.data_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.kernels = self._load_metadata()

    def _load_metadata(self):
        if not self.metadata_path.exists():
            item = resources.files('sora.data').joinpath("planet_kernels.json")
            # read from package resource and write to disk
            data = item.read_bytes()
            self.metadata_path.write_bytes(data)
            logging.debug(f"SORA: Planetary Kernel standard file copied to user data path: {config.data_path}")
        with open(self.metadata_path, "r") as f:
            return json.load(f)

    def _save_metadata(self):
        with open(self.metadata_path, "w") as f:
            json.dump(self.kernels, f, indent=2)

    def add_kernel(self, name: str, url: str, overwrite: bool = False):
        if name.lower() not in self.kernels:
            if overwrite:
                logging.warning(f"SORA: {name} already exists. Overwriting")
            else:
                logging.warning(f"SORA: {name} already exists. Skipping")
                return
        self.kernels[name.lower()] = {"url": url, "filename": url.split("/")[-1]}
        self._save_metadata()

    def get_planetary_kernel(self, name: str) -> str:
        if name.lower() not in self.kernels:
            raise ValueError(f"Kernel '{name}' not found in metadata.")

        info = self.kernels[name.lower()]
        local_path = self.download_dir / info["filename"]

        if not local_path.exists():
            self._download_file(info["url"], local_path)

        return str(local_path)

    def _download_file(self, url: str, local_path: Path):
        try:
            logging.info(f"SORA: Downloading planetary kernel from {url}")
            response = requests.get(url, stream=True)
            response.raise_for_status()

            total = int(response.headers.get('content-length', 0))
            desc = local_path.name
            with open(local_path, 'wb') as f, tqdm(
                desc = desc,
                total = total,
                unit='B',
                unit_scale = True,
                unit_divisor = 1024,
            ) as bar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))
            logging.info(f"SORA: Downloaded kernel to {local_path}")
        except Exception as e:
            logging.error(f"SORA: Failed to download {url}: {e}")
            raise

    def list_kernels(self):
        return [(name, data["url"]) for name, data in self.kernels.items()]