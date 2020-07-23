#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import logging
import subprocess
import sys

version = '0.0.3'


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
    parser.add_argument('-q', '--quiet', action='store_true')
    args = parser.parse_args()

    if not args.quiet:
        logging.basicConfig(
            format='%(message)s',
            level=logging.INFO,
            stream=sys.stdout)

    with concurrent.futures.ProcessPoolExecutor() as pool:
        futures = {
            pool.submit(_is_healthy, container): container
            for container in _inspect_containers(args.container)
        }
        while futures:
            for future in concurrent.futures.as_completed(futures.keys()):
                result = future.result()
                container_id = futures.pop(future)
                if result is False:
                    future = pool.submit(_is_healthy, container_id)
                    futures[future] = container_id


if __name__ == '__main__':
    main()
