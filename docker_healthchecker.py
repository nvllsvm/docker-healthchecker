#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import subprocess
import sys

version = '0.0.9'

_LOGGER = logging.getLogger('docker-healthchecker')


async def _inspect_containers(container_ids):
    process = await asyncio.create_subprocess_exec(
        'docker', 'inspect', *container_ids,
        stdout=subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    return json.loads(stdout.decode().strip())


async def _is_healthy(inspect_data):
    container_id = inspect_data['Id']
    healthcheck = inspect_data['Config'].get('Healthcheck')
    if healthcheck:
        _LOGGER.info('Checking: %s', container_id)
        hc_type = healthcheck['Test'][0]
        hc_args = healthcheck['Test'][1:]
        if hc_type == 'CMD-SHELL':
            process = await asyncio.create_subprocess_exec(
                'docker',
                'exec', container_id, '/bin/sh', '-c', hc_args[0],
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
            returncode = await process.wait()
        elif hc_type == 'CMD':
            process = await asyncio.create_subprocess_exec(
                'docker', 'exec', container_id, *hc_args,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL
            )
            returncode = await process.wait()
        else:
            raise NotImplementedError(hc_type)
        healthy = not bool(returncode)
        _LOGGER.info(
            '%s: %s',
            'Healthy' if healthy else 'Unhealthy',
            container_id,
        )
        return inspect_data, healthy
    else:
        _LOGGER.info('No health check: %s', container_id)
        return inspect_data, None


async def _check_containers(containers):
    pending = [
        _is_healthy(container)
        for container in await _inspect_containers(containers)
    ]
    while pending:
        done, pending = await asyncio.wait(
            pending, return_when=asyncio.FIRST_COMPLETED)
        pending = list(pending)
        for f in done:
            inspect_data, result = f.result()
            if result is False:
                pending.append(_is_healthy(inspect_data))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('container', nargs='*', default='')
    parser.add_argument('-q', '--quiet', default=False, action='store_true',
                        help='Suppress output')
    parser.add_argument('-t', '--timeout', type=int,
                        metavar='SECONDS',
                        help=('Time to wait before failing. '
                              'Waits indefinitely when not specified'))
    parser.add_argument('--version', action='version', version=version)
    args = parser.parse_args()

    containers = set()
    if not sys.stdin.isatty():
        containers.update(sys.stdin.read().splitlines())
    containers.update(args.container)

    if not containers:
        parser.error('no containers specified')
        parser.exit()

    if not args.quiet:
        logging.basicConfig(
            format='%(message)s',
            level=logging.INFO,
            stream=sys.stdout)

    try:
        asyncio.run(asyncio.wait_for(
            _check_containers(containers), timeout=args.timeout
        ))
    except asyncio.TimeoutError:
        sys.exit(1)


if __name__ == '__main__':
    main()
