# Docker Healthchecker
Wait for Docker healthchecks to be healthy

## Installation
```
pip install docker-healthchecker
```

## Usage Examples
### Single container
```
docker-healthchecker <container_id>
```

### Docker Compose
```
docker-healthchecker $(docker-compose ps -aq)
```
