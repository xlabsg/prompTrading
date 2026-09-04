#!/bin/bash
# Helper script to run integration tests in Docker Compose environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN}  PrompTrading - Integration Tests${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""

# Check if Docker Compose is running
echo -e "${YELLOW}Checking Docker Compose services...${NC}"
COMPOSE_DIR="$(cd "$(dirname "$0")/../../infra/compose" && pwd)"
cd "$COMPOSE_DIR"

if ! docker compose -f docker-compose.dev.yml ps &>/dev/null; then
    echo -e "${RED}Error: Docker Compose is not running!${NC}"
    echo ""
    echo "Please start the dev environment first:"
    echo "  cd infra/compose"
    echo "  ./update.sh"
    echo ""
    exit 1
fi

# Check if required services are up
REQUIRED_SERVICES=("api" "worker")
for service in "${REQUIRED_SERVICES[@]}"; do
    if ! docker compose -f docker-compose.dev.yml ps "$service" | grep -q "running"; then
        echo -e "${RED}Error: Service '$service' is not running!${NC}"
        echo ""
        echo "Start all services:"
        echo "  cd infra/compose"
        echo "  ./update.sh"
        echo ""
        exit 1
    fi
done

echo -e "${GREEN}✓ All required services are running${NC}"
echo ""

# Run tests
echo -e "${YELLOW}Running integration tests...${NC}"
echo ""

TEST_ARGS="${@:-tests/test_integration_workflow.py -v -m integration}"

docker compose -f docker-compose.dev.yml exec -T api pytest $TEST_ARGS

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}==================================================${NC}"
    echo -e "${GREEN}  All tests passed! ✓${NC}"
    echo -e "${GREEN}==================================================${NC}"
else
    echo -e "${RED}==================================================${NC}"
    echo -e "${RED}  Some tests failed!${NC}"
    echo -e "${RED}==================================================${NC}"
    echo ""
    echo "To view detailed logs:"
    echo "  cd infra/compose"
    echo "  docker compose -f docker-compose.dev.yml logs worker | tail -50"
fi

exit $EXIT_CODE
