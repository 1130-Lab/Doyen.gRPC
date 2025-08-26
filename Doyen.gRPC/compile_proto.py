import os
import os.path
import shutil
import subprocess
import sys

def compile_protos():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Output directory for generated Python files
    output_dir = os.path.join(current_dir, "generated")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Verify paths
    print(f"Solution root: {current_dir}")
    print(f"Output directory: {output_dir}")
    
    # Run the protoc compiler with grpcio-tools
    # Use solution root as proto_path so imports work correctly
    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--proto_path={current_dir}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        "-odescriptor.pb",
        "*.proto"
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    
    # Add error output capture
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=current_dir)
    
    if result.returncode == 0:
        print(f"Proto compilation successful for {current_dir}!")
        build_docs(output_dir)
        algosPath = os.path.join("../", "Doyen.Scripts.Algorithms")
        print(f"Distributing algos files to {algosPath}")
        distribute_protos("generated", "algos", algosPath)
        distribute_protos("generated", "common", algosPath)
        indicatorsPath = os.path.join("../", "Doyen.Scripts.Indicators")
        print(f"Distributing indicators files to {indicatorsPath}")
        distribute_protos("generated", "charts", indicatorsPath)
        distribute_protos("generated", "common", indicatorsPath)
        return True
    else:
        print(f"Proto compilation failed with code {result.returncode}")
        print(f"Error output: {result.stderr}")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return False

def distribute_protos(src, fltr, dst):
    """Distribute generated protos to the specified path"""
    try:
        files = os.listdir(src)
        for file in files:
            if file.startswith(fltr) and file.endswith(".py"):
                src_file = os.path.join(src, file)
                dst_file = os.path.join(dst, file)
                if not os.path.exists(dst_file) or not os.path.samefile(src_file, dst_file):
                    print(f"Copying {src_file} to {dst_file}")
                    shutil.copy(src_file, dst_file)
    except:
        print(f"Failed to distribute protos from {src} to {dst}.")
        return False

def build_docs(path):
    """Try to build documentation using sabledocs if available"""
    try:
        result = subprocess.run(["sabledocs"], capture_output=True, text=True)
        if result.returncode == 0:
            print("Documentation build successful!")
            return True
        else:
            print("Documentation build failed.")
            print(f"Error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("Documentation build skipped. Install sabledocs if you need documentation: pip install sabledocs")
        return True

if __name__ == "__main__":
    # Check if grpcio-tools is installed
    try:
        import grpc_tools.protoc
        
        # Compile common.proto first (dependency)
        success = compile_protos()
        
        if success:
            print("All proto files compiled successfully!")
        else:
            print("Some proto files failed to compile.")
            sys.exit(1)
            
    except ImportError:
        print("ERROR: grpcio-tools package is not installed.")
        print("Please run: pip install grpcio-tools")
        sys.exit(1)
