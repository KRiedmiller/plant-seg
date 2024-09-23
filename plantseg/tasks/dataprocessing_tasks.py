from plantseg.core.image import ImageLayout, PlantSegImage, SemanticType
from plantseg.core.voxelsize import VoxelSize
from plantseg.functionals.dataprocessing import (
    fix_over_under_segmentation_from_nuclei,
    image_gaussian_smoothing,
    image_rescale,
    relabel_segmentation,
    remove_false_positives_by_foreground_probability,
    set_biggest_instance_to_zero,
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


def _compute_slices(rectangle, crop_z: tuple[int, int], shape):
    """
    Compute slices for cropping based on a given rectangle and z-slices.
    """
    z_slice = slice(*crop_z)
    if rectangle is None:
        return z_slice, slice(0, shape[1]), slice(0, shape[2])

    x_start = max(rectangle[0, 1], 0)
    x_end = min(rectangle[2, 1], shape[1])
    x_slice = slice(x_start, x_end)

    y_start = max(rectangle[0, 2], 0)
    y_end = min(rectangle[2, 2], shape[2])
    y_slice = slice(y_start, y_end)
    return z_slice, x_slice, y_slice


def _cropping(data, crop_slices):
    """
    Apply cropping on the provided data based on the computed slices.
    """
    return data[crop_slices]


@task_tracker
def image_cropping_task(image: PlantSegImage, rectangle=None, crop_z: tuple[int, int] = (0, 100)) -> PlantSegImage:
    """
    Crop the image based on the given rectangle and z-slices.

    Args:
        image (PlantSegImage): The image to be cropped.
        rectangle (Optional): Rectangle defining the region to crop.
        crop_z (tuple[int, int]): Z-slice range for cropping.

    Returns:
        PlantSegImage: The cropped image.
    """
    data = image.get_data()

    # Compute crop slices
    crop_slices = _compute_slices(rectangle, crop_z, data.shape)

    # Perform cropping on the data
    cropped_data = _cropping(data, crop_slices)

    # Create and return a new PlantSegImage object from the cropped data
    cropped_image = image.derive_new(cropped_data, name=f"{image.name}_cropped")

    return cropped_image


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


@task_tracker
def set_biggest_instance_to_zero_task(image: PlantSegImage, instance_could_be_zero: bool = False) -> PlantSegImage:
    """
    Task to set the largest segment in a segmentation image to zero.

    Args:
        image (PlantSegImage): Segmentation image to process.
        instance_could_be_zero (bool): If True, 0 might be an instance label, add 1 to all labels before processing.

    Returns:
        PlantSegImage: New segmentation image with largest instance set to 0.
    """
    if not (image.semantic_type == SemanticType.SEGMENTATION or image.semantic_type == SemanticType.LABEL):
        raise ValueError("Input image must be a segmentation or mask image.")
    data = image.get_data()
    print(f"Processing {image.name} with shape {data.shape} and max {data.max()}, min {data.min()}.")
    new_data = set_biggest_instance_to_zero(data, instance_could_be_zero=instance_could_be_zero)
    new_image = image.derive_new(new_data, name=f"{image.name}_bg0")
    return new_image


@task_tracker
def relabel_segmentation_task(image: PlantSegImage, background: int | None = None) -> PlantSegImage:
    """
    Task to relabel a segmentation image contiguously, ensuring non-touching segments with the same ID are relabeled.

    Args:
        image (PlantSegImage): Segmentation image to process.

    Returns:
        PlantSegImage: New segmentation image with relabeled instances.
    """
    if not (image.semantic_type == SemanticType.SEGMENTATION or image.semantic_type == SemanticType.LABEL):
        raise ValueError("Input image must be a segmentation or mask image.")
    data = image.get_data()
    new_data = relabel_segmentation(data, background=background)
    new_image = image.derive_new(new_data, name=f"{image.name}_relabeled")
    return new_image
