from plantseg.__version__ import __version__
from plantseg.image import Image
from pydantic import BaseModel, Field
from typing import Callable
from enum import Enum
import yaml
import json
from pathlib import Path
from uuid import uuid4, UUID


class NodeType(str, Enum):
    NODE = "node"
    ROOT = "root"
    LEAF = "leaf"


class Task(BaseModel):
    func: str
    images_inputs: dict
    parameters: dict
    list_private_parameters: list[str]
    outputs: list[str]
    node_type: NodeType
    id: UUID = Field(default_factory=uuid4)

    """
    A task is a single operation in the workflow. It is defined by:
    
    Attributes:
        func (str): The name of the function to be executed
        images_inputs (dict): A image input represent a Image object. 
            The key is the name of the parameter in the function, and the value is the name of the image.
        parameters (dict): The kwargs parameters of the workflow function.
        list_private_parameters (list[str]): A list of the names of the private parameters.
        outputs (list[str]): A list of the names of the output images.
        node_type (NodeType): The type of the node in the workflow (ROOT, LEAF, NODE)
        id (UUID): A unique identifier for the task.
        
    """


class DAG(BaseModel):
    plantseg_version: str = Field(default=__version__)
    inputs: list[dict[str, str]] | dict[str, str] = Field(default_factory=dict)
    list_tasks: list[Task] = Field(default_factory=list)

    """
    This model represents the Directed Acyclic Graph (DAG) of the workflow.
    
    Attributes:
        plantseg_version (str): The version of PlantSeg used to create the workflow.
        inputs (dict[str, Any]): A dictionary of the inputs of the workflow. For example path to the images and other runtime parameters.
        list_tasks (list[Task]): A list of the tasks in the workflow.
    
    """

    @property
    def list_inputs(self):
        return list(self.inputs.keys())


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class FuncsHandler(metaclass=SingletonMeta):
    def __init__(self):
        self._funcs = {}

    def register_func(self, func):
        self._funcs[func.__name__] = func

    def get_func(self, name):
        return self._funcs[name]

    def list_funcs(self):
        return list(self._funcs.keys())


class WorkflowHandler:
    """
    Container for a workflow. It stores the functions, the a list of tasks.
    """

    def __init__(self):
        self._funcs = FuncsHandler()
        self._dag = DAG()

    @property
    def dag(self) -> DAG:
        return self._dag

    @property
    def func_registry(self) -> FuncsHandler:
        return self._funcs

    def register_func(self, func):
        self._funcs.register_func(func)

    def add_task(
        self,
        func: Callable,
        images_inputs: dict,
        parameters: dict,
        list_private_parameters: list[str],
        outputs: list[str],
        node_type: NodeType,
    ):
        assert func.__name__ in self._funcs.list_funcs(), f"Function {func.__name__} not registered"

        task = Task(
            func=func.__name__,
            images_inputs=images_inputs,
            parameters=parameters,
            list_private_parameters=list_private_parameters,
            outputs=outputs,
            node_type=node_type,
        )
        self._dag.list_tasks.append(task)

    def add_input(self, name: str):
        def _unique_input(name, id: int = 0):
            new_name = f"{name}_{id}"
            if new_name not in self._dag.list_inputs:
                return new_name

            return _unique_input(name, id + 1)

        unique_name = _unique_input(name)
        self._dag.inputs[unique_name] = "FILL THIS VALUE TO RUN THE WORKFLOW"
        return unique_name

    def clean_dag(self):
        self._dag = DAG()

    def prune_dag(self):
        """
        Remove all the tasks that are not connected to the leaf nodes.
        """
        dag_copy = self._dag.model_copy(deep=True)

        # Initialize the reachable set with the leaf nodes
        reachable = set()
        reachable_inputs = set()
        for task in dag_copy.list_tasks:
            if task.node_type == NodeType.LEAF:
                for inp_key in task.images_inputs.values():
                    reachable.add(task.id)
                    reachable_inputs.add(inp_key)

        safety_counter = 0
        size_reachable = len(reachable)
        while True:
            # For each task check if the outputs is connected to the reachable set
            # if so, add the task to the reachable set
            for task in dag_copy.list_tasks:
                for out_key in task.outputs:
                    if out_key in reachable_inputs:
                        reachable.add(task.id)
                        for inp_key in task.images_inputs.values():
                            reachable_inputs.add(inp_key)

            safety_counter += 1
            if safety_counter > 1_000_000:
                raise ValueError("Infinite loop in the pruning of the DAG")

            # If the size of the reachable set did not change, we are done pruning
            if size_reachable == len(reachable):
                break
            size_reachable = len(reachable)

        self._dag.list_tasks = [task for task in dag_copy.list_tasks if task.id in reachable]

    def save_to_yaml(self, path: Path | str):
        self.prune_dag()
        dag_dict = json.loads(self._dag.model_dump_json())

        if isinstance(path, str):
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.dump(dag_dict, f)

    def from_yaml(self, path: Path) -> "WorkflowHandler":
        with open(path, "r") as f:
            dag_dict = yaml.load(f, Loader=yaml.FullLoader)

        self._dag = DAG(**dag_dict)
        return self


workflow_handler = WorkflowHandler()


def task_tracker(
    func: Callable | None = None,
    is_multioutput=False,
    is_root=False,
    is_leaf=False,
    list_inputs: list[str] | None = None,
    list_private_params: list[str] | None = None,
):
    """
    Decorator
    """

    if is_root and is_leaf:
        raise ValueError("A node cannot be both root and leaf at the same time")

    if is_root:
        node_type = NodeType.ROOT
    elif is_leaf:
        node_type = NodeType.LEAF
    else:
        node_type = NodeType.NODE

    list_inputs = list_inputs or []
    list_private_params = list_private_params or []

    def _inner_decorator(func):
        workflow_handler.register_func(func)

        def wrapper(*args, **kwargs):
            assert len(args) == 0, "Workflow functions should not have positional arguments"

            images_inputs = {}
            parameters = {}

            for name, arg in kwargs.items():
                if isinstance(arg, Image):
                    images_inputs[name] = arg.unique_name

                elif name in list_inputs:
                    input_name = workflow_handler.add_input(name)
                    images_inputs[name] = input_name

                else:
                    parameters[name] = arg

            for private_param in list_private_params:
                if private_param not in parameters:
                    raise ValueError(f"Private parameter {private_param} not found in the function parameters")

            # Execute the function
            out_image = func(*args, **kwargs)

            # Parse the output
            if out_image is None:
                list_outputs = []

            elif isinstance(out_image, Image):
                list_outputs = [out_image.unique_name]

            elif is_multioutput and isinstance(out_image, tuple):
                list_outputs = []
                for i, img in enumerate(out_image):
                    if not isinstance(img, Image):
                        raise ValueError(f"Output {i} is not an Image object, but {type(img)}")
                    list_outputs.append(img.unique_name)
            else:
                raise ValueError(
                    f"Output of a workflow function should be one of None, Image or Tuple of Images. Got {type(out_image)}"
                )

            for name in list_outputs:
                if name in images_inputs.values():
                    raise ValueError(
                        f"Function {func.__name__} has an output image with the same name as an input image: {name}"
                    )

            workflow_handler.add_task(
                func=func,
                images_inputs=images_inputs,
                parameters=parameters,
                list_private_parameters=list_private_params,
                outputs=list_outputs,
                node_type=node_type,
            )
            return out_image

        return wrapper

    if func is None:
        return _inner_decorator

    return _inner_decorator(func)
