import logging

# This worker needs access to the baker and the package_builder.
from editor.baker import bake_master_data
from editor.package_builder import chunk_master_data

def bake_and_chunk_worker(generator_settings: dict, master_data_path: str, logger: logging.Logger):
    """
    A worker function that first bakes the master data and then chunks it.
    This is designed to be run in a separate process to avoid freezing the UI.
    """
    try:
        logger.info("WORKER: Starting master bake...")
        bake_master_data(generator_settings, logger)
        logger.info("WORKER: Master bake complete. Starting chunking...")
        chunk_master_data(master_data_path, logger)
        logger.info("WORKER: Chunking complete.")
        return True
    except Exception as e:
        # Use exc_info=True to log the full traceback from the worker process
        logger.critical(f"WORKER: An exception occurred during bake/chunk process: {e}", exc_info=True)
        return False