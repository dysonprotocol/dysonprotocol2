#!/usr/bin/env bash

set -e
set -x

echo "Formatting protobuf files"
find ./proto -name "*.proto" -exec clang-format -i {} \;

echo "Deleting old generated files"
find ./api -name "*.pulsar.go" -delete
find ./api -name "*.pb.go" -delete
find ./x -name "*.pb.go" -delete
find ./x -name "*.pb.gw.go" -delete


# clean up old temp files
rm -rf ./client/docs/swagger-ui/swagger-gen || true
rm -rf ./client/docs/proto-json-schema || true
rm -rf ./client/ts || true

# Generate the swagger docs
mkdir -p ./client/docs/swagger-ui/swagger-gen
mkdir -p ./client/docs/proto-json-schema

cd ./proto
for d in $(find . -name '*.proto' -print0 | xargs -0 -n1 dirname | sort | uniq); do
  # skip if $dir is a subdirectory of ./cosmos/app/v1alpha1
  if [[ "$d" =~ ^./cosmos/app/v1alpha1 ]]; then
    echo "Skipping $d (subdirectory of ./cosmos/app/v1alpha1)"
    continue
  fi
  echo "Generating swagger files for $d"

  # only generate swagger files for tx.proto, query.proto, and service.proto
  proto_files=$(find "${d}" -maxdepth 1 \( -name 'tx.proto' -o -name 'query.proto' -o -name 'service.proto' -o -name 'reflection.proto' \))
  for file in $proto_files; do
    buf generate --template buf.gen.swagger.yaml $file
  done


  # only generate jsonschema files for tx.proto and query.proto
  proto_files=$(find "${d}" -maxdepth 1 \( -name 'tx.proto' -o -name 'query.proto' \))
  for file in $proto_files; do
    dir=$(dirname $file)
    echo "Generating jsonschema for $file"
    buf generate --template buf.gen.jsonschema.yaml $file
    # move the jsonschema file from ./proto-json-schema to ./proto-json-schema/$dir
    # from ./proto/proto-json-schema/*.json 
    # to ./proto/proto-json-schema/$dir/*.json
    mkdir -p ../client/docs/proto-json-schema/$dir
    ls -la ./proto-json-schema
    mv ./proto-json-schema/*.json ../client/docs/proto-json-schema/$dir/ || true
  done

done

cd ..
pwd

# Python function to remove specific description keys for `Any` and `A URL/resource`
python - <<EOF
print("Starting python script")
import json
import glob
import os

def walk_and_modify(obj):
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            if key == 'description' and isinstance(obj.get(key, None), str) and (obj.get(key, '').startswith('\`Any\`') or obj.get(key, '').startswith('A URL/resource')):
                print(f"Removing description")
                del obj[key]
            elif key == 'name' and isinstance(obj.get(key, None), str) and obj.get(key, '').startswith('pagination'):
                print(f"Removing pagination description: {obj}")
                del obj['description']
            else:
                if key in obj:
                    walk_and_modify(obj[key])
    elif isinstance(obj, list):
        for item in obj:
            walk_and_modify(item)

def update_operation_ids(data):
    title = data.get('info', {}).get('title', '')
    if not title.endswith('.proto'):
        print(f"Skipping invalid title: {title}")
        return
    proto_dir = os.path.dirname(title)
    package = proto_dir.replace('/', '.').rstrip('.')
    paths = data.get('paths', {})
    for path_key, path_val in list(paths.items()):
        for method_key, op in path_val.items():
            old_id = op.get('operationId')
            if not old_id or '_' not in old_id:
                continue
            service, method_name = old_id.split('_', 1)
            if service == 'Query':
                request_name = service + method_name + 'Request'
                new_id = package + '.' + request_name
                op['operationId'] = new_id
                print(f"Updating {old_id} -> {new_id}")
            elif service == 'Msg':
                request_name = service + method_name
                new_id = package + '.' + request_name
                op['operationId'] = new_id
                paths[new_id] = path_val
                del paths[path_key]
                print(f"Updating {old_id} -> {new_id}")

def process_file(json_file):
    with open(json_file, 'r') as file:
        data = json.load(file)
    walk_and_modify(data)
    update_operation_ids(data)
    with open(json_file, 'w') as file:
        json.dump(data, file, indent=2)
        file.flush()

for file in glob.glob('./client/docs/swagger-ui/swagger-gen/**/*.json', recursive=True):
    print(f"Processing {file}")
    process_file(file)

print("Processing JSON schema files")

def process_jsonschema_file(json_file):
    with open(json_file, 'r') as file:
        data = json.load(file)
    
    # Extract package path from file location
    # e.g., client/docs/proto-json-schema/cosmos/distribution/v1beta1/SomeFile.json -> cosmos.distribution.v1beta1
    relative_path = os.path.relpath(json_file, './client/docs/proto-json-schema')
    package_path = os.path.dirname(relative_path).replace('/', '.')
    
    # Skip if there's no package path (files in root)
    if not package_path or package_path == '.':
        print(f"Skipping {json_file} because it has no package path")
        return
    
    definitions = data.get('definitions', {})
    if not definitions:
        print(f"Skipping {json_file} because it has no definitions")
        return
    
    # Extract the definition name from \$ref
    ref = data.get('\$ref', '')
    if not ref.startswith('#/definitions/'):
        print(f"Skipping {json_file} because it has no \$ref")
        return
    
    current_def_name = ref.replace('#/definitions/', '')
    
    # Check if the definition exists
    if current_def_name not in definitions:
        print(f"Skipping {json_file} because {current_def_name} is not in definitions")
        return
    
    current_def_content = definitions[current_def_name]
    
    # Create new definition name with package prefix
    new_def_name = f"{package_path}.{current_def_name}"
    
    print(f"Renaming definition {current_def_name} -> {new_def_name} in {json_file}")
    
    # Update the definitions object
    del data['definitions'][current_def_name]
    data['definitions'] = {new_def_name: current_def_content, **definitions}
    
    # Update the \$ref to point to the new definition
    data['\$ref'] = f"#/definitions/{new_def_name}"
    
    # Write back the updated file
    with open(json_file, 'w') as file:
        json.dump(data, file, indent=4)
        file.flush()

# Process all JSON schema files
for file in glob.glob('./client/docs/proto-json-schema/**/*.json', recursive=True):
    print(f"Processing JSON schema file {file}")
    process_jsonschema_file(file)
EOF

# Group by RPC methods using external Python script
python3 ./scripts/group_rpc_methods.py

# combine swagger files
# uses nodejs package `swagger-combine`.
# all the individual swagger files need to be configured in `config.json` for merging
swagger-combine ./client/docs/config.json -o ./client/docs/swagger-ui/swagger.yaml -f yaml --continueOnConflictingPaths true --includeDefinitions true


cd ./client/docs/swagger-ui/swagger-gen
tree * -J > index.json
tree * --prune -H "./" > index.html
cd -


cd ./client/docs/proto-json-schema 
tree . -J > index.json
tree . --prune -H "./" > index.html
cd -


###
# Generate TypeScript (protobuf-es + connect-es)
###
echo "Generating TypeScript client code (protobuf-es + connect-es)"

cd ./proto

# Ensure output dir exists
mkdir -p ../client/ts

for d in $(find . -name '*.proto' -print0 | xargs -0 -n1 dirname | sort | uniq); do
  # skip if $dir is a subdirectory of ./cosmos/app/v1alpha1
  if [[ "$d" =~ ^./cosmos/app/v1alpha1 ]]; then
    echo "Skipping $d (subdirectory of ./cosmos/app/v1alpha1)"
    continue
  fi

  # Only generate for tx.proto, query.proto, and service.proto
  proto_files=$(find "${d}" -maxdepth 1 \( -name 'tx.proto' -o -name 'query.proto' -o -name 'service.proto' \))
  for file in $proto_files; do
    echo "Generating TS for $file"
    buf generate --template ./buf.gen.es.yaml $file
  done
done

cd ..


###
# Generate go proto code for dysonprotocol modules
###


echo "Generating gogo proto code for dysonprotocol modules"
dyson_proto_dirs=$(find ./proto/dysonprotocol -path -prune -o -name '*.proto' -print0 | xargs -0 -n1 dirname | sort | uniq)
for dir in $dyson_proto_dirs; do
  for file in $(find "${dir}" -maxdepth 1 -name '*.proto'); do
    buf generate --template ./proto/buf.gen.gogo.yaml $file
    buf generate --template ./proto/buf.gen.pulsar.yaml $file
  done
done


# move proto files to the right places
cp -r ./dysonprotocol.com/* ./
rm -rf ./dysonprotocol.com

cp -r ./api/dysonprotocol.com/x/* ./api/
rm -rf ./api/dysonprotocol.com



echo "Proto generation complete!" 
