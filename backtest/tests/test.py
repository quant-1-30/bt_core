import sys

def example_function():
    # Get the current frame
    current_frame = sys._getframe(0)
    
    # Print information about the current frame
    print("Current function name:", current_frame.f_code.co_name)
    print("Current line number:", current_frame.f_lineno)
    print("Local variables:", current_frame.f_locals)

    cur_1 = sys._getframe(1)
    print("Current function name1:", cur_1.f_code.co_name)
    print("Current line number1:", cur_1.f_lineno)
    print("Local variables1:", cur_1.f_locals)

example_function()

