from plantseg.tasks import task_tracker
from plantseg.plantseg_image import PlantSegImage, import_image, save_image
from pathlib import Path


@task_tracker(
    is_root=True,
    list_private_params=["semantic_type", "stack_layout"],
    list_inputs=["input_path"],
)
def import_image_task(
    input_path: Path,
    key: str,
    image_name: str,
    semantic_type: str,
    stack_layout: str,
    m_slicing: str | None = None,
) -> PlantSegImage:
    """
    Task wrapper creating a PlantSegImage object from an image file.
    """
    return import_image(
        path=input_path,
        key=key,
        image_name=image_name,
        semantic_type=semantic_type,
        stack_layout=stack_layout,
        m_slicing=m_slicing,
    )


@task_tracker(is_leaf=True, list_inputs=["output_directory", "output_file_name"])
def export_image_task(
    image: PlantSegImage,
    output_directory: Path,
    output_file_name: str,
    custom_key: str,
    scale_to_origin: bool,
    file_format: str = "tiff",
    dtype: str = "uint16",
) -> None:
    """
    Task wrapper for saving an PlantSegImage object to disk.
    """
    save_image(
        image=image,
        directory=output_directory,
        file_name=output_file_name,
        custom_key=custom_key,
        scale_to_origin=scale_to_origin,
        file_format=file_format,
        dtype=dtype,
    )
    return None


@task_tracker
def mock_task1(image: PlantSegImage) -> tuple[PlantSegImage, PlantSegImage]:
    image2 = image.derive_new(image.data, name=f"{image.name}_m1")
    image3 = image.derive_new(image.data, name=f"{image.name}_m2")
    return image2, image3


@task_tracker
def mock_task2(image: PlantSegImage, image2: PlantSegImage) -> PlantSegImage:
    return image.derive_new(image.data, name=f"{image.name}_m3")
