# Working with workflows

Plantseg can create and execute workflows for batch processing.
A new workflow can be created in the napari gui, and it can be executed
using the commandline interface.

## Creating a workflow

To create a new workflow, one must process an example image through the napari GUI.
Once the result has been exported, a button to `Export Workflow` will appear
in the input/output tab in napari.
Plantseg then creates a `yaml` file to repeat the workflow for any number of files.

The workflow includes input/output paths and naming schemes, so before the new
workflow is useable, those need to be adjusted using the editor:

## Editing a workflow

Plantseg comes with an editor for the workflow yaml files.
It can be opened through the napari gui (`Edit Workflow`),
or from the cli:

```bash
plantseg --editor [workflow.yaml]
```

![Workflow gui](https://github.com/kreshuklab/plant-seg/raw/refs/heads/assets/images/workflow_gui_overview.webp)

### Input/Output

On the left, the input/output section is shown.
You can specify a directory as `input_path` to use all images in this
directory, or just a single image.

The name_pattern defines how the exported images are named.
You can use the placeholders `{file_name}` to reference the input file's name,
or `{image_name}` to reference the layer name napari would have given the image.

### Tasks

The right side displays all tasks the workflow contains.
Most of them expose some modifiable values.

If you need to modify something else, the editor should show you the proper
name of the field, so you can edit the file in your favorite text editor.

## Running a workflow

To finally run a workflow after you have modified the paths to your liking, please use the cli:

```bash
plantseg --config your_workflow_file.yaml
```
