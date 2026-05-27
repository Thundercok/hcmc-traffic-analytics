import torch
from torch import Tensor
from scipy.ndimage import gaussian_filter
from typing import Optional, List, Tuple


def get_id(x: str) -> int:
    # shanghaitech
    if "_" in x:
        return int(x.split(".")[0].split("_")[1])
    # qnrf
    elif "img" in x:
        return int(x.split(".")[0].split("_")[1])
    # oto
    elif "image-" in x:
        return int(x.split(".")[0].split("-")[-1])
    # nwpu
    else:
        return int(x.split(".")[0])


def generate_density_map(label: Tensor, height: int, width: int, sigma: Optional[float] = None, num_classes: int = 1) -> Tensor:
    """
    generate the density map based on the dot annotations provided by the label.
    supports multi-class labels if label has 3 columns (x, y, class_id).
    """
    density_map = torch.zeros((num_classes, height, width), dtype=torch.float32)

    if len(label) > 0:
        label_ = label.long()
        
        # Check if label has class information (N, 3)
        if label_.shape[1] == 3 and num_classes > 1:
            # Clamp coordinates
            label_[:, 0] = label_[:, 0].clamp(min=0, max=width - 1)
            label_[:, 1] = label_[:, 1].clamp(min=0, max=height - 1)
            
            # Clamp class ids to be safe
            label_[:, 2] = label_[:, 2].clamp(min=0, max=num_classes - 1)

            # Assign to specific class channels
            # We iterate to handle potential duplicate points at same location properly if needed,
            # but for simple binary map setting:
            for c in range(num_classes):
                mask = (label_[:, 2] == c)
                if mask.any():
                    pts = label_[mask]
                    density_map[c, pts[:, 1], pts[:, 0]] = 1.0

        else:
            # Default behavior (single class or ignore class info if num_classes=1)
            assert label_.shape[1] >= 2, f"label should have at least 2 columns, got {label.shape}."
            label_[:, 0] = label_[:, 0].clamp(min=0, max=width - 1)
            label_[:, 1] = label_[:, 1].clamp(min=0, max=height - 1)
            density_map[0, label_[:, 1], label_[:, 0]] = 1.0

    if sigma is not None:
        assert sigma > 0, f"sigma should be positive if not None, got {sigma}."
        # Apply gaussian filter to each channel
        for c in range(num_classes):
            density_map[c] = torch.from_numpy(gaussian_filter(density_map[c], sigma=sigma))

    return density_map


def collate_fn(batch: List[Tensor]) -> Tuple[Tensor, List[Tensor], Tensor]:
    batch = list(zip(*batch))
    images = batch[0]
    assert len(images[0].shape) == 4, f"images should be a 4D tensor, got {images[0].shape}."
    if len(batch) == 4:  # image, label, density_map, image_name
        images = torch.cat(images, 0)
        points = batch[1]  # list of lists of tensors, flatten it
        points = [p for points_ in points for p in points_]
        densities = torch.cat(batch[2], 0)
        image_names = batch[3]  # list of lists of strings, flatten it
        image_names = [name for names_ in image_names for name in names_]

        return images, points, densities, image_names

    elif len(batch) == 3:  # image, label, density_map
        images = torch.cat(images, 0)
        points = batch[1]
        points = [p for points_ in points for p in points_]
        densities = torch.cat(batch[2], 0)

        return images, points, densities
    
    elif len(batch) == 2:  # image, image_name. NWPU test dataset
        images = torch.cat(images, 0)
        image_names = batch[1]
        image_names = [name for names_ in image_names for name in names_]

        return images, image_names

    else:
        images = torch.cat(images, 0)

        return images
