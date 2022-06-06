import asyncio
import sys
import numpy
from flipdisc.framework.app import Application

async def update(app):
    # Generate width x height numbers between 0 and 1
    rand = numpy.random.random(app.output.shape)

    # Threshold rand at 0.5
    app.output[rand <= 0.5] = 0
    app.output[rand > 0.5] = 255

    # Send result to the output stream.
    await app.send_output(app.output)

async def main(cfg_path):
    # Create an application named "noise" and use the sample config included.
    app = Application("noise", config=cfg_path)
    await app.setup_redis()

    # App specific setup.
    out_cfg = app.config['output_stream']
    app.output = numpy.zeros((out_cfg['height'], out_cfg['width']), numpy.uint8)

    # Create a callback to be called each 1/30 seconds.
    app.add_periodic_callback(update, 1/30.)

    # Start the event loop.
    try:
        await app.run()
    finally:
        await app.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        pass