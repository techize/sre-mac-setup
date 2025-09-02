#!/bin/bash

# Environment (e.g., uat, production)
ENV=$1

if [ -z "$ENV" ]; then
    echo "Usage: $0 <environment>"
    echo "Example: $0 uat"
    exit 1
fi

# Determine AWS Profile and DB Identifiers based on environment
if [ "$ENV" == "uat" ]; then
    AWS_PROFILE="default" # Assuming default profile is for UAT
    SOURCE_DB_IDENTIFIER="uat-devops-tools"
    TARGET_DB_IDENTIFIER="uat-openmetadata"
    DUMP_FILE="openmetadata_uat_dump.sql"
elif [ "$ENV" == "production" ]; then
    AWS_PROFILE="production"
    SOURCE_DB_IDENTIFIER="production-devops-tools"
    TARGET_DB_IDENTIFIER="production-openmetadata"
    DUMP_FILE="openmetadata_prod_dump.sql"
else
    echo "Error: Invalid environment '$ENV'. Must be 'uat' or 'production'."
    exit 1
fi

DB_NAME_TO_DUMP="openmetadata" # This remains constant

echo "--- Getting connection details for source DB: ${SOURCE_DB_IDENTIFIER} (${ENV}) ---"

# Get Endpoint
SOURCE_DB_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier "${SOURCE_DB_IDENTIFIER}" \
    --profile "${AWS_PROFILE}" \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text)

if [ -z "${SOURCE_DB_ENDPOINT}" ]; then
    echo "Error: Could not retrieve endpoint for ${SOURCE_DB_IDENTIFIER}. Exiting."
    exit 1
fi
echo "Endpoint: ${SOURCE_DB_ENDPOINT}"

# Get Port
SOURCE_DB_PORT=$(aws rds describe-db-instances \
    --db-instance-identifier "${SOURCE_DB_IDENTIFIER}" \
    --profile "${AWS_PROFILE}" \
    --query 'DBInstances[0].Endpoint.Port' \
    --output text)

if [ -z "${SOURCE_DB_PORT}" ]; then
    echo "Error: Could not retrieve port for ${SOURCE_DB_IDENTIFIER}. Exiting."
    exit 1
fi
echo "Port: ${SOURCE_DB_PORT}"

# Get Username and Password from Secrets Manager
SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "database/${SOURCE_DB_IDENTIFIER}/${DB_NAME_TO_DUMP}" \
    --profile "${AWS_PROFILE}" \
    --query SecretString \
    --output text)

if [ -z "${SECRET_JSON}" ]; then
    echo "Error: Could not retrieve secret for database/${SOURCE_DB_IDENTIFIER}/${DB_NAME_TO_DUMP}. Exiting."
    exit 1
fi

SOURCE_DB_USERNAME=$(echo "${SECRET_JSON}" | jq -r '.username')
SOURCE_DB_PASSWORD=$(echo "${SECRET_JSON}" | jq -r '.password')

if [ -z "${SOURCE_DB_USERNAME}" ] || [ -z "${SOURCE_DB_PASSWORD}" ]; then
    echo "Error: Could not parse username or password from secret. Exiting."
    exit 1
fi
echo "Username: ${SOURCE_DB_USERNAME}"

echo "--- Checking if database '${DB_NAME_TO_DUMP}' exists on ${SOURCE_DB_IDENTIFIER} ---"

# Check if the database exists by trying to select it
DB_EXISTS=$(mysql -h "${SOURCE_DB_ENDPOINT}" -P "${SOURCE_DB_PORT}" -u "${SOURCE_DB_USERNAME}" -p"${SOURCE_DB_PASSWORD}" \
    -e "SHOW DATABASES LIKE '${DB_NAME_TO_DUMP}';" | grep "${DB_NAME_TO_DUMP}")

if [ -z "${DB_EXISTS}" ]; then
    echo "Error: Database '${DB_NAME_TO_DUMP}' does NOT exist on ${SOURCE_DB_IDENTIFIER}. Cannot dump."
    exit 1
else
    echo "Database '${DB_NAME_TO_DUMP}' found. Proceeding with dump."
fi

echo "--- Running mysqldump for database: ${DB_NAME_TO_DUMP} ---"

# Run mysqldump
mysqldump \
    --single-transaction \
    --set-gtid-purged=OFF \
    --column-statistics=0 \
    -h "${SOURCE_DB_ENDPOINT}" \
    -P "${SOURCE_DB_PORT}" \
    -u "${SOURCE_DB_USERNAME}" \
    -p"${SOURCE_DB_PASSWORD}" \
    "${DB_NAME_TO_DUMP}" > "${DUMP_FILE}"

if [ $? -eq 0 ]; then
    echo "Successfully dumped database '${DB_NAME_TO_DUMP}' to ${DUMP_FILE}"
else
    echo "Error: mysqldump failed. Check the output above for details."
    exit 1
fi

echo "--- Script finished ---"