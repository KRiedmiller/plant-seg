from plantseg.core.image import ImageLayout, PlantSegImage
from plantseg.core.voxelsize import VoxelSize
from plantseg.functionals.dataprocessing import (
    fix_over_under_segmentation_from_nuclei,
    image_gaussian_smoothing,
    image_rescale,
    remove_false_positives_by_foreground_probability,
)
from plantseg.tasks import task_tracker


@task_tracker
def gaussian_smoothing_task(image: PlantSegImage, sigma: float) -> PlantSegImage:
    """
    Apply Gaussian smoothing to a PlantSegImage object.

    Args:
        image (PlantSegImage): input image
        sigma (float): standard deviation of the Gaussian kernel

    """
    if image.is_multichannel:
        raise ValueError("Gaussian smoothing is not supported for multichannel images.")

    data = image.get_data()
    smoothed_data = image_gaussian_smoothing(data, sigma=sigma)
    new_image = image.derive_new(smoothed_data, name=f"{image.name}_smoothed")
    return new_image


@task_tracker
def set_voxel_size_task(image: PlantSegImage, voxel_size: tuple[float, float, float]) -> PlantSegImage:
    """Set the voxel size of an image.

    Args:
        image (PlantSegImage): input image
        voxel_size (tuple[float, float, float]): new voxel size

    """
    new_voxel_size = VoxelSize(voxels_size=voxel_size)
    new_image = image.derive_new(
        image._data,
        name=f"{image.name}_set_voxel_size",
        voxel_size=new_voxel_size,
        original_voxel_size=new_voxel_size,
    )
    return new_image


@task_tracker
def image_rescale_to_shape_task(image: PlantSegImage, new_shape: tuple[int, ...], order: int = 0) -> PlantSegImage:
    """Rescale an image to a new shape.

    Args:
        image (PlantSegImage): input image
        new_shape (tuple[int, ...]): new shape of the image
        order (int): order of the interpolation
    """
    if image.image_layout == ImageLayout.YX:
        scaling_factor = (new_shape[1] / image.shape[0], new_shape[2] / image.shape[1])
        spatial_scaling_factor = (1.0, scaling_factor[0], scaling_factor[1])
    elif image.image_layout == ImageLayout.ZYX:
        scaling_factor = (new_shape[0] / image.shape[0], new_shape[1] / image.shape[1], new_shape[2] / image.shape[2])
        spatial_scaling_factor = scaling_factor
    elif image.image_layout == ImageLayout.CYX:
        scaling_factor = (1.0, new_shape[1] / image.shape[1], new_shape[2] / image.shape[2])
        spatial_scaling_factor = (1.0, scaling_factor[1], scaling_factor[2])
    elif image.image_layout == ImageLayout.CZYX:
        scaling_factor = (
            1.0,
            new_shape[0] / image.shape[1],
            new_shape[1] / image.shape[2],
            new_shape[2] / image.shape[3],
        )
        spatial_scaling_factor = scaling_factor[1:]
    elif image.image_layout == ImageLayout.ZCYX:
        scaling_factor = (
            new_shape[0] / image.shape[0],
            1.0,
            new_shape[1] / image.shape[2],
            new_shape[2] / image.shape[3],
        )
        spatial_scaling_factor = (scaling_factor[0], scaling_factor[2], scaling_factor[3])

    out_data = image_rescale(image.get_data(), scaling_factor, order=order)

    if image.has_valid_voxel_size():
        out_voxel_size = image.voxel_size.voxelsize_from_factor(spatial_scaling_factor)
    else:
        out_voxel_size = VoxelSize()

    new_image = image.derive_new(out_data, name=f"{image.name}_reshaped", voxel_size=out_voxel_size)
    return new_image


@task_tracker
def image_rescale_to_voxel_size_task(image: PlantSegImage, new_voxel_size: VoxelSize, order: int = 0) -> PlantSegImage:
    """Rescale an image to a new voxel size.

    If the voxel size is not defined in the input image, use the set voxel size task to set the voxel size.

    Args:
        image (PlantSegImage): input image
        new_voxel_size (VoxelSize): new voxel size
        order (int): order of the interpolation

    """
    spatial_scaling_factor = image.voxel_size.scalefactor_from_voxelsize(new_voxel_size)

    if image.image_layout == ImageLayout.YX:
        scaling_factor = (spatial_scaling_factor[1], spatial_scaling_factor[2])
    elif image.image_layout == ImageLayout.CYX:
        scaling_factor = (1.0, spatial_scaling_factor[1], spatial_scaling_factor[2])
    elif image.image_layout == ImageLayout.ZYX:
        scaling_factor = spatial_scaling_factor
    elif image.image_layout == ImageLayout.CZYX:
        scaling_factor = (1.0, *spatial_scaling_factor)
    elif image.image_layout == ImageLayout.ZCYX:
        scaling_factor = (spatial_scaling_factor[0], 1.0, *spatial_scaling_factor[1:])

    out_data = image_rescale(image.get_data(), scaling_factor, order=order)
    new_image = image.derive_new(out_data, name=f"{image.name}_rescaled", voxel_size=new_voxel_size)
    return new_image


@task_tracker
def remove_false_positives_by_foreground_probability_task(
    segmentation: PlantSegImage, foreground: PlantSegImage, threshold: float
) -> PlantSegImage:
    """Remove false positives from a segmentation based on the foreground probability.

    Args:
        segmentation (PlantSegImage): input segmentation
        foreground (PlantSegImage): input foreground probability
        threshold (float): threshold value

    """
    if segmentation.shape != foreground.shape:
        raise ValueError("Segmentation and foreground probability must have the same shape.")

    out_data = remove_false_positives_by_foreground_probability(
        segmentation.get_data(), foreground.get_data(), threshold
    )
    new_image = segmentation.derive_new(out_data, name=f"{segmentation.name}_fg_filtered")
    return new_image


@task_tracker
def fix_over_under_segmentation_from_nuclei_task(
    cell_seg: PlantSegImage,
    nuclei_seg: PlantSegImage,
    threshold_merge: float = 0.33,
    threshold_split: float = 0.66,
    quantiles_nuclei: tuple[float, float] = (0.3, 0.99),
    boundary: PlantSegImage | None = None,
) -> PlantSegImage:
    """
    Task function to fix over- and under-segmentation in cell segmentation based on nuclear segmentation.

    This function is used to run the over- and under-segmentation correction within a task management system.
    It uses the segmentation arrays and nuclear information to merge and split cell regions. This task ensures
    that the provided `cell_seg` and `nuclei_seg` have matching shapes and processes the data accordingly.

    Args:
        cell_seg (PlantSegImage): Input cell segmentation as a `PlantSegImage` object.
        nuclei_seg (PlantSegImage): Input nuclear segmentation as a `PlantSegImage` object.
        threshold_merge (float, optional): Threshold for merging cells based on the overlap with nuclei. Default is 0.33.
        threshold_split (float, optional): Threshold for splitting cells based on the overlap with nuclei. Default is 0.66.
        quantiles_nuclei (tuple[float, float], optional): Quantiles used to filter nuclei by size. Default is (0.3, 0.99).
        boundary (PlantSegImage | None, optional): Optional boundary probability map. If not provided, a constant map is used.

    Returns:
        PlantSegImage: A new `PlantSegImage` object containing the corrected cell segmentation.
    """
    if cell_seg.shape != nuclei_seg.shape:
        raise ValueError("Cell and nuclei segmentation must have the same shape.")

    out_data = fix_over_under_segmentation_from_nuclei(
        cell_seg.get_data(),
        nuclei_seg.get_data(),
        threshold_merge=threshold_merge,
        threshold_split=threshold_split,
        quantiles_nuclei=quantiles_nuclei,
        boundary=boundary.get_data() if boundary else None,
    )
    new_image = cell_seg.derive_new(out_data, name=f"{cell_seg.name}_nuc_fixed")
    return new_image
