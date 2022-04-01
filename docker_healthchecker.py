#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import sys

version = '0.2.2'

_LOGGER = logging.getLogger('docker-healthchecker')


async def _inspect_containers(container_ids):
    process = await asyncio.create_subprocess_exec(
        'docker', 'inspect', *container_ids,
        stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    return json.loads(stdout.decode().strip())


async def _is_healthy(inspect_data):
    container_id = inspect_data['Id']
    container_name = inspect_data['Name']
    healthcheck = inspect_data['Config'].get('Healthcheck')
    if healthcheck:
        _LOGGER.info('Checking: %s (%s)', container_name, container_id)
        hc_type = healthcheck['Test'][0]
        hc_args = healthcheck['Test'][1:]
        try:
            if hc_type == 'CMD-SHELL':
                process = await asyncio.create_subprocess_exec(
                    'docker',
                    'exec', container_id, '/bin/sh', '-c', hc_args[0],
                    stderr=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE
                )
            elif hc_type == 'CMD':
                process = await asyncio.create_subprocess_exec(
                    'docker', 'exec', container_id, *hc_args,
                    stderr=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE
                )
            else:
                raise NotImplementedError(hc_type)
            pending = [
                asyncio.create_task(process.stdout.readline(), name='stdout'),
                asyncio.create_task(process.stderr.readline(), name='stderr'),
            ]
            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    name = task.get_name()
                    result = task.result()
                    if result:
                        _LOGGER.debug(
                            '%s (%s) %s %r',
                            container_name, container_id, name, result)
                        pending.add(
                            asyncio.create_task(
                                getattr(process, name).readline(), name=name))
            returncode = await process.wait()
        except asyncio.CancelledError:
            _LOGGER.warning('Timeout exceeded: %s (%s)',
                            container_name, container_id)
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
            raise
        healthy = not bool(returncode)
        _LOGGER.info(
            '%s: %s (%s)',
            'Healthy' if healthy else 'Unhealthy',
            container_name, container_id,
        )
        return inspect_data, healthy
    else:
        _LOGGER.info('No health check: %s (%s)', container_name, container_id)
        return inspect_data, None


async def _timeout(timeout):
    await asyncio.sleep(timeout)
    raise asyncio.TimeoutError


async def _check_containers(containers, timeout=None):
    pending = [
        asyncio.ensure_future(_is_healthy(container))
        for container in await _inspect_containers(containers)
    ]

    if timeout:
        pending.append(asyncio.ensure_future(_timeout(timeout)))

    timedout = False
    while pending:
        if timeout and len(pending) == 1:
            break
        done, pending = await asyncio.wait(
            pending, return_when=asyncio.FIRST_COMPLETED)
        pending = list(pending)
        for f in done:
            try:
                inspect_data, result = f.result()
            except asyncio.TimeoutError:
                timedout = True
            else:
                if result is False:
                    pending.append(
                        asyncio.ensure_future(_is_healthy(inspect_data)))
        if timedout and pending:
            for p in pending:
                try:
                    p.cancel()
                    await p
                except asyncio.CancelledError:
                    pass
            raise asyncio.TimeoutError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('container', nargs='*', default='')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-q', '--quiet', default=False, action='store_true',
                       help='Suppress output')
    group.add_argument('--verbose', action='store_true', help='Verbose output')
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
            level=logging.DEBUG if args.verbose else logging.INFO,
            stream=sys.stdout)

    try:
        asyncio.run(_check_containers(containers, args.timeout))
    except asyncio.TimeoutError:
        sys.exit(1)


if __name__ == '__main__':
    main()
