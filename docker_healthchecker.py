#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import logging
import subprocess
import sys

version = '0.0.1'

logging.basicConfig(
    format='%(message)s',
    level=logging.INFO,
    stream=sys.stdout)


def _inspect_containers(container_ids):
    result = subprocess.run(
        ['docker', 'inspect', *container_ids],
        stdout=subprocess.PIPE,
        check=True
    )
    return json.loads(result.stdout.decode().strip())


def _is_healthy(inspect_data):
    logger = logging.getLogger(__name__)

    container_id = inspect_data['Id']
    healthcheck = inspect_data['Config'].get('Healthcheck')
    if healthcheck:
        logger.info('Checking: %s', container_id)
        hc_type = healthcheck['Test'][0]
        hc_args = healthcheck['Test'][1:]
        if hc_type == 'CMD-SHELL':
            result = subprocess.run(
                ['docker', 'exec', container_id, '/bin/sh', '-c', hc_args[0]],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        elif hc_type == 'CMD':
            result = subprocess.run(
                ['docker', 'exec', container_id, *hc_args],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
        else:
            raise NotImplementedError(hc_type)
        healthy = not bool(result.returncode)
        logger.info(
            '%s: %s',
            'Healthy' if healthy else 'Unhealthy',
            container_id,
        )
        return healthy
    else:
        logger.info('No health check: %s', container_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('container', nargs='+')
    args = parser.parse_args()

    with concurrent.futures.ProcessPoolExecutor() as pool:
        futures = {
            pool.submit(_is_healthy, container): container
            for container in _inspect_containers(args.container)
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is False:
                pool.submit(_is_healthy, futures[future])


if __name__ == '__main__':
    main()
