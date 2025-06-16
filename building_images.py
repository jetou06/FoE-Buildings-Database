import json
import re
import logging
from typing import Dict, Optional
import config
import streamlit as st

# Use logger from config
logger = config.logger


class BuildingImageManager:
    """Manages building image URL mappings from FoE game assets."""
    
    def __init__(self, metadata_file: str = "metadata-zz0-129.json", image_file: str = "img-zz0-94.json"):
        self.metadata_file = metadata_file
        self.image_file = image_file
        self.building_images: Dict[str, str] = {}
        self._load_building_images()
    
    @st.cache_data
    def _load_building_images(_self) -> None:
        """Load and process building images from JSON files."""
        try:
            # Load metadata and image files
            with open(_self.metadata_file, "r", encoding='utf-8') as f:
                metadata = json.load(f)
            
            with open(_self.image_file, "r", encoding='utf-8') as f:
                image_data = json.load(f)
            
            # Create list of building ID mappings for W_ prefixed buildings
            building_mappings = []
            for building in metadata:
                if building["asset_id"].startswith("W_"):
                    # Transform W_ to W_SS_ for image matching
                    transformed_id = re.sub(r"W_", "W_SS_", building["asset_id"])
                    building_mappings.append((transformed_id, building['asset_id']))
                elif building["asset_id"].startswith("R_"):
                    # Transform R_ to R_SS_ for image matching
                    transformed_id = re.sub(r"R_", "R_SS_", building["asset_id"])
                    building_mappings.append((transformed_id, building['asset_id']))
                elif building["asset_id"].startswith("L_"):
                    # Transform S_ to S_SS_ for image matching
                    transformed_id = re.sub(r"L_", "L_SS_", building["asset_id"])
                    building_mappings.append((transformed_id, building['asset_id']))
            
            # Create dictionary mapping building IDs to image URLs
            # Sort building mappings by transformed_id length (longest first) to prioritize exact matches
            building_mappings_sorted = sorted(building_mappings, key=lambda x: len(x[0]), reverse=True)
            
            for img_path, img_data in image_data.items():
                # Extract filename from path
                img_filename = img_path.split("/")[-1] if "/" in img_path and (img_path.endswith(".png") or img_path.endswith(".jpg")) else None
                
                if img_filename is not None:
                    # Remove file extension for precise matching
                    img_name_without_ext = img_filename.rsplit('.', 1)[0]
                    
                    # Check if any building ID matches this image
                    for transformed_id, original_id in building_mappings_sorted:
                        # Simple substring check, but with longest IDs first to avoid conflicts
                        if transformed_id in img_name_without_ext:
                            # Additional check: ensure it's not a partial match by checking boundaries
                            # Find the position of the match
                            match_pos = img_name_without_ext.find(transformed_id)
                            match_end = match_pos + len(transformed_id)
                            
                            # Check if the match is at word boundaries (not preceded/followed by alphanumeric)
                            is_valid_match = True
                            if match_pos > 0 and img_name_without_ext[match_pos - 1].isalnum():
                                is_valid_match = False
                            if match_end < len(img_name_without_ext) and img_name_without_ext[match_end].isalnum():
                                is_valid_match = False
                            
                            if is_valid_match:
                                # Construct the full image URL
                                processed_img_path = re.sub(r'(.*?)\.png', rf'\1-{img_data}.png', img_path)
                                full_url = 'https://foezz.innogamescdn.com/assets' + processed_img_path
                                _self.building_images[original_id] = full_url
                                break

            logger.info(f"Loaded {len(_self.building_images)} building image mappings")
            
        except FileNotFoundError as e:
            logger.error(f"Image data files not found: {e}")
            _self.building_images = {}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON files: {e}")
            _self.building_images = {}
        except Exception as e:
            logger.error(f"Unexpected error loading building images: {e}")
            _self.building_images = {}
    
    def get_building_image_url(self, building_id: str) -> Optional[str]:
        """
        Get the image URL for a building by its ID.
        
        Args:
            building_id: The building ID to look up
            
        Returns:
            The image URL if found, None otherwise
        """
        return self.building_images.get(building_id)
    
    def has_image(self, building_id: str) -> bool:
        """
        Check if a building has an associated image.
        
        Args:
            building_id: The building ID to check
            
        Returns:
            True if image exists, False otherwise
        """
        return building_id in self.building_images
    
    def get_all_mappings(self) -> Dict[str, str]:
        """
        Get all building ID to image URL mappings.
        
        Returns:
            Dictionary of building_id -> image_url mappings
        """
        return self.building_images.copy()
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about loaded images.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "total_images": len(self.building_images),
            "unique_buildings": len(set(self.building_images.keys()))
        }


# Global instance for easy access
_image_manager = None
@st.cache_resource
def get_image_manager() -> BuildingImageManager:
    """Get the global BuildingImageManager instance."""
    global _image_manager
    if _image_manager is None:
        _image_manager = BuildingImageManager()
    return _image_manager

def get_building_image_url(building_id: str) -> Optional[str]:
    """
    Convenience function to get building image URL.
    
    Args:
        building_id: The building ID to look up
        
    Returns:
        The image URL if found, None otherwise
    """
    return get_image_manager().get_building_image_url(building_id)

def has_building_image(building_id: str) -> bool:
    """
    Convenience function to check if building has image.
    
    Args:
        building_id: The building ID to check
        
    Returns:
        True if image exists, False otherwise
    """
    return get_image_manager().has_image(building_id) 