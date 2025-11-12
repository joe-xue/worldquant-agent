# extract_functions.py

import inspect
import platform_functions

def extract_function_structure(module):
    functions = {}
    for name, obj in inspect.getmembers(module, predicate=inspect.isfunction):
        if not name.startswith('_'):  # Ignore private functions
            signature = inspect.signature(obj)
            functions[name] = {
                'parameters': [param.name for param in signature.parameters.values()],
                'return_type': str(signature.return_annotation) if signature.return_annotation else 'None'
            }
    return functions

if __name__ == "__main__":
    function_structure = extract_function_structure(platform_functions)
    for name, details in function_structure.items():
        print(f"Function: {name}")
        print(f"  Parameters: {', '.join(details['parameters']) if details['parameters'] else 'None'}")
        print(f"  Return Type: {details['return_type']}\n")