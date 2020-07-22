#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import logging
import subprocess

LOGGER = logging.getLogger('docker-healthchecker')

version = '0.0.1'


def _inspect_containers(container_ids):
    result = subprocess.run(
        ['docker', 'inspect', *container_ids],
        stdout=subprocess.PIPE,
        check=True
    )
    return json.loads(result.stdout.decode().strip())


def _is_healthy(inspect_data):
    container_id = inspect_data['Id']
    LOGGER.info('%s - checking', container_id)
    healthcheck = inspect_data['Config'].get('Healthcheck')
    if healthcheck:
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
        LOGGER.info(
            '%s - %s',
            container_id,
            'healthy' if healthy else 'unhealthy'
        )
        return healthy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('container', nargs='+')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

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
