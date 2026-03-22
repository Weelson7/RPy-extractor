"""Unity asset discovery indexer for completeness tracking."""
import json
import struct
from pathlib import Path
from typing import Callable
from dataclasses import dataclass, asdict
from collections import defaultdict

from logging_utils import emit_log


# Unity class type IDs (common types)
UNITY_CLASS_TYPES = {
    1: "GameObject",
    2: "Component",
    4: "Transform",
    6: "RectTransform",
    8: "Rigidbody",
    9: "ConstantForce",
    13: "Camera",
    14: "Material",
    15: "Renderer",
    18: "Animation",
    19: "MeshFilter",
    21: "OcclusionCullingSettings",
    23: "MeshCollider",
    25: "OffMeshLink",
    28: "ParticleSystem",
    33: "MeshCollider",
    41: "WheelCollider",
    43: "ZoneCollider",
    54: "Animator",
    56: "AudioListener",
    57: "AudioSource",
    58: "AudioClip",
    65: "OcclusionArea",
    68: "Tree",
    74: "Canvas",
    81: "AudioReverbZone",
    82: "AudioChorusFilter",
    83: "AudioDistortionFilter",
    84: "AudioEchoFilter",
    85: "AudioHighPassFilter",
    86: "AudioLowPassFilter",
    87: "AudioReverbFilter",
    89: "WindZone",
    96: "Skybox",
    104: "GuiLayer",
    108: "GUITexture",
    111: "GUIText",
    114: "PhysicMaterial",
    115: "SphereCollider",
    116: "CapsuleCollider",
    117: "BoxCollider",
    119: "Mesh",
    120: "Shader",
    121: "TextAsset",
    122: "SceneAsset",
    124: "AnimationClip",
    125: "RuntimeAnimatorController",
    128: "Material",
    130: "Texture3D",
    134: "Sprite",
    135: "Cubemap",
    137: "AudioMixer",
    141: "Cubemap",
    142: "AudioMixerController",
    144: "AvatarMask",
    145: "MixerController",
    147: "RuntimeAnimatorController",
    150: "Prefab",
}

# Media type classification based on class ID
MEDIA_TYPE_MAP = {
    "Texture2D": "image",
    "Texture3D": "image",
    "Cubemap": "image",
    "Sprite": "image",
    "Texture": "image",
    "AudioClip": "audio",
    "VideoClip": "video",
    "Mesh": "model",
    "SkinnedMeshRenderer": "model",
    "Avatar": "model",
    "AnimationClip": "animation",
    "RuntimeAnimatorController": "animation",
    "Material": "material",
    "Shader": "shader",
    "TextAsset": "text",
    "SceneAsset": "scene",
}


@dataclass
class DiscoveredAsset:
    """Represents a discovered asset in a container."""
    class_id: int
    class_name: str
    path_id: int
    name: str
    size: int
    container: str
    media_type: str | None = None
    offset: int = 0


@dataclass
class DiscoveryIndex:
    """Complete discovery index for a game root."""
    discovered_assets: list[DiscoveredAsset]
    containers_scanned: list[str]
    discovery_stats: dict
    scan_timestamp: str


def get_class_name(class_id: int) -> str:
    """Get human-readable class name from Unity class ID."""
    return UNITY_CLASS_TYPES.get(class_id, f"UnknownClass{class_id}")


def classify_media_type(class_name: str) -> str | None:
    """Classify asset by its class type."""
    for key, media_type in sorted(MEDIA_TYPE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if key in class_name:
            return media_type
    return None


def scan_unity_containers(game_root: Path, progress: Callable[[str], None] | None = None) -> list[Path]:
    """Find all Unity container files in a game root.
    
    Unity containers include:
    - globalgamemanagers
    - sharedassets*.assets
    - level* bundles
    - CAB-* bundles
    
    Returns:
        List of discovered container file paths.
    """
    containers = []
    search_patterns = [
        "globalgamemanagers",
        "globalgamemanagers.assets",
        "sharedassets*.assets",
        "cam_*.assets",
        "level*.assets",
        "sceneasset-*.assets",
        "*_Data",  # Data directory indicator
    ]
    
    if progress:
        progress(f"[DISCOVERY] Scanning for Unity containers in {game_root}")
    
    # Look for containers recursively
    for pattern in search_patterns:
        found = list(game_root.glob(f"**/{pattern}"))
        containers.extend(found)
    
    # Also find bundle-like files (CAB-*, *.bundle, *.bin)
    for pattern in ["CAB-*", "*.bundle"]:
        found = list(game_root.glob(f"**/{pattern}"))
        containers.extend(found)
    
    # Deduplicate and filter to files
    containers = sorted(set(Path(c) for c in containers if c.is_file()))
    
    if progress:
        progress(f"[DISCOVERY] Found {len(containers)} container candidates")
    
    return containers


def parse_unity_asset_header(container_path: Path) -> dict | None:
    """Parse Unity asset file header to get basic metadata.
    
    Returns dict with header info or None if not a valid Unity asset.
    """
    try:
        with open(container_path, "rb") as f:
            # Try to read UnityFS header
            header = f.read(16)
            if len(header) < 16:
                return None
            
            # Check for UnityFS signature
            if header[:6] == b"UnityFS":
                return {
                    "format": "UnityFS",
                    "version": struct.unpack(">I", header[6:10])[0] if len(header) >= 10 else 0,
                    "size": container_path.stat().st_size,
                }
            
            # Check for serialized format (common in older unity)
            if header[:4] == b"\x00\x00\x00\x00" or header[:2] == b"\xff\xfe":
                return {
                    "format": "Serialized",
                    "size": container_path.stat().st_size,
                }
            
            return None
    except Exception:
        return None


def discover_assets_from_container(
    container_path: Path,
    progress: Callable[[str], None] | None = None,
) -> list[DiscoveredAsset]:
    """Discover assets within a container file.
    
    For now, this uses a simplified approach that documents what was scanned.
    Full UnityFS/serialized format parsing will be implemented in later slices
    when importers are available.
    """
    discovered = []
    
    try:
        header_info = parse_unity_asset_header(container_path)
        if not header_info:
            if progress:
                progress(f"[DISCOVERY] Skipping {container_path.name} - not a recognizable Unity asset")
            return discovered
        
        if progress:
            progress(f"[DISCOVERY] Read {container_path.name} ({header_info.get('format', 'Unknown')})")
        
        # In Slice 2, we create a discovery record for the container itself
        # In Slice 3+, actual asset enumeration will use specialized parsers
        
        discovered.append(
            DiscoveredAsset(
                class_id=0,
                class_name="Container",
                path_id=0,
                name=f"Container: {container_path.name}",
                size=container_path.stat().st_size,
                container=str(container_path),
                media_type="container",
                offset=0,
            )
        )
    
    except Exception as e:
        if progress:
            progress(f"[DISCOVERY] Error scanning {container_path.name}: {e}")
    
    return discovered


def build_discovery_index(
    game_root: Path,
    progress: Callable[[str], None] | None = None,
) -> DiscoveryIndex:
    """Build complete discovery index for a game.
    
    Scans all Unity containers and discovers all discoverable assets,
    creating an exhaustive index with container mappings.
    """
    if progress:
        progress("[DISCOVERY] Starting Unity discovery index build")
    
    discovered_assets = []
    containers_scanned = []
    
    # Find all containers
    containers = scan_unity_containers(game_root, progress)
    
    # Discover assets in each container
    for container in containers:
        try:
            container_rel = container.relative_to(game_root)
            containers_scanned.append(str(container_rel))
            
            if progress:
                progress(f"[DISCOVERY] Scanning container {container_rel}")
            
            assets = discover_assets_from_container(container, progress)
            discovered_assets.extend(assets)
        
        except Exception as e:
            if progress:
                progress(f"[DISCOVERY] Error processing {container}: {e}")
    
    # Build statistics
    stats = {
        "total_discovered": len(discovered_assets),
        "total_containers_scanned": len(containers_scanned),
        "by_class_id": defaultdict(int),
        "by_media_type": defaultdict(int),
    }
    
    for asset in discovered_assets:
        stats["by_class_id"][asset.class_name] += 1
        if asset.media_type:
            stats["by_media_type"][asset.media_type] += 1
    
    # Convert to regular dicts for serialization
    stats["by_class_id"] = dict(stats["by_class_id"])
    stats["by_media_type"] = dict(stats["by_media_type"])
    
    if progress:
        progress(f"[DISCOVERY] Discovery complete: {len(discovered_assets)} assets discovered")
    
    from datetime import datetime
    return DiscoveryIndex(
        discovered_assets=discovered_assets,
        containers_scanned=containers_scanned,
        discovery_stats=stats,
        scan_timestamp=datetime.utcnow().isoformat(),
    )


def write_discovery_manifest(
    index: DiscoveryIndex,
    output_dir: Path,
) -> Path:
    """Write discovery manifest to JSON file.
    
    Returns path to manifest file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = output_dir / "discovery_manifest.json"
    
    manifest_data = {
        "timestamp": index.scan_timestamp,
        "containers_scanned": index.containers_scanned,
        "discovered_count": len(index.discovered_assets),
        "discovery_stats": index.discovery_stats,
        "assets": [
            {
                "class_id": asset.class_id,
                "class_name": asset.class_name,
                "path_id": asset.path_id,
                "name": asset.name,
                "size": asset.size,
                "container": asset.container,
                "media_type": asset.media_type,
                "offset": asset.offset,
            }
            for asset in index.discovered_assets
        ],
    }
    
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    
    return manifest_path
