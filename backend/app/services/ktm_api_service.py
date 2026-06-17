"""
KTM-2000 API Service - integrates Ekranchik with KTM-2000 MES API.
"""
import logging
import socket
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class KtmApiService:
    """Client for fetching products/profiles and photos from KTM-2000 MES backend"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self._cached_base_url: Optional[str] = None

    def _get_docker_gateway_ip(self) -> Optional[str]:
        """Dynamically computes the gateway IP of the current container (assumed to end with .1)"""
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            parts = ip.split('.')
            if len(parts) == 4:
                parts[3] = '1'
                return '.'.join(parts)
        except Exception as e:
            logger.debug(f"[KTM API] Could not determine Docker gateway IP: {e}")
        return None

    async def _check_url(self, url: str) -> bool:
        """Helper to verify if a candidate KTM-2000 base URL is responsive"""
        url_clean = url.rstrip('/')
        for path in ("/api/health", "/api/products"):
            try:
                # Use a very short timeout for quick availability checks
                response = await self.client.get(f"{url_clean}{path}", timeout=1.0)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
        return False

    async def get_working_base_url(self) -> str:
        """Detects and returns a working base URL among candidates, caching the result"""
        if self._cached_base_url:
            return self._cached_base_url

        candidates = []
        # 1. Prioritize explicitly configured URL (user-defined IP/port)
        if settings.KTM_BACKEND_URL:
            candidates.append(settings.KTM_BACKEND_URL)
        
        # 2. Add docker container name (in case they share a network)
        candidates.append("http://ktm2000-nginx-prod")

        # 3. Add dynamically computed gateway IP
        gateway_ip = self._get_docker_gateway_ip()
        if gateway_ip:
            candidates.append(f"http://{gateway_ip}:8082")

        # 4. Standard candidates for developer machine & VM environments
        defaults = [
            "http://host.docker.internal:8082",
            "http://172.17.0.1:8082",
            "http://172.21.0.1:8082",
            "http://172.23.0.1:8082",
            "http://localhost:8082",
            "http://localhost:8010"
        ]
        for d in defaults:
            if d not in candidates:
                candidates.append(d)

        logger.info(f"[KTM API] Detecting working KTM-2000 backend URL among candidates: {candidates}")
        for url in candidates:
            if await self._check_url(url):
                logger.info(f"[KTM API] Successfully connected to KTM-2000 at: {url}")
                self._cached_base_url = url
                return url

        # Fallback to configured setting if everything fails
        logger.warning(f"[KTM API] None of the candidates responded. Falling back to default: {settings.KTM_BACKEND_URL}")
        return settings.KTM_BACKEND_URL

    async def _get_mapped_url(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        base = await self.get_working_base_url()
        return f"{base.rstrip('/')}/static/{path}"

    async def _map_product_to_profile(self, prod: Dict[str, Any]) -> Dict[str, Any]:
        """Maps KTM-2000 Product schema to Ekranchik Profile schema"""
        sku = prod.get("sku", "")
        photo_thumb = await self._get_mapped_url(prod.get("photo_thumb"))
        photo_full = await self._get_mapped_url(prod.get("photo_full"))

        # Parse dates
        created_at = prod.get("created_at") or "2026-01-01T00:00:00"
        updated_at = prod.get("updated_at") or "2026-01-01T00:00:00"

        return {
            "id": prod.get("id", 0),
            "name": sku, # Ekranchik profiles are identified by name (which matches KTM-2000 sku)
            "quantity_per_hanger": prod.get("quantity_per_hanger"),
            "length": prod.get("length_mm"),
            "notes": prod.get("notes") or prod.get("name"), # fallback to product name
            "photo_thumb": photo_thumb,
            "photo_full": photo_full,
            "usage_count": 0,
            "created_at": created_at,
            "updated_at": updated_at
        }

    async def get_all_profiles(self) -> List[Dict[str, Any]]:
        """Fetch all products from KTM-2000 and map them to Ekranchik profiles"""
        base_url = await self.get_working_base_url()
        url = f"{base_url.rstrip('/')}/api/products"
        try:
            logger.info(f"[KTM API] Fetching all products from: {url}")
            response = await self.client.get(url)
            if response.status_code == 200:
                products = response.json()
                if not isinstance(products, list):
                    logger.error(f"[KTM API] Invalid response format from {url}: expected list, got {type(products)}")
                    return []
                
                mapped_profiles = []
                for p in products:
                    if not isinstance(p, dict):
                        logger.warning(f"[KTM API] Skipping non-dict product item: {p}")
                        continue
                    sku = p.get("sku")
                    if not sku:
                        logger.warning(f"[KTM API] Skipping product item with empty SKU: {p}")
                        continue
                    mapped_profiles.append(await self._map_product_to_profile(p))
                return mapped_profiles
            else:
                logger.error(f"[KTM API] Failed to fetch products from {url}: status={response.status_code}, response={response.text[:200]}")
                return []
        except (httpx.ConnectError, httpx.TimeoutException) as conn_err:
            logger.error(f"[KTM API] Connection/timeout error connecting to KTM-2000 at {url}: {conn_err}. Resetting cache.")
            self._cached_base_url = None
            return []
        except Exception as e:
            logger.error(f"[KTM API] Unexpected error fetching products from {url}: {e}", exc_info=True)
            return []

    async def search_profiles(self, query: str) -> List[Dict[str, Any]]:
        """Fetch matching products from KTM-2000 search API"""
        try:
            all_profs = await self.get_all_profiles()
            if not query:
                return all_profs
                
            query_lower = query.lower()
            results = []
            for p in all_profs:
                name = p.get("name", "").lower()
                notes = (p.get("notes") or "").lower()
                if query_lower in name or query_lower in notes:
                    results.append(p)
            return results
        except Exception as e:
            logger.error(f"[KTM API] Error searching KTM-2000 products: {e}", exc_info=True)
            return []

    async def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Get product by SKU/name from KTM-2000"""
        try:
            all_profs = await self.get_all_profiles()
            for p in all_profs:
                if p.get("name") == name:
                    return p
            return None
        except Exception as e:
            logger.error(f"[KTM API] Error getting profile {name}: {e}")
            return None


ktm_api_service = KtmApiService()
