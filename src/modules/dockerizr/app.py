import logging

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from generator import DockerfileGenerator, GunicornGenerator, RequirementsAnalyzr

from configuration import DockerizrConfiguration

logger.info("Initializing the FastAPI app for dockerizr")
app = FastAPI()


@app.post("/generate_gunicorn_files/")
async def generate_gunicorn_files(conf: DockerizrConfiguration):
    try:
        logger.debug("Attempting to generate Gunicorn files")
        GunicornGenerator(conf).generate_gunicorn()
        # Assuming the generation was successful, we can send a success message.
        return JSONResponse(
            content={"message": "Gunicorn files generated successfully."},
            status_code=200,
        )
    except Exception as e:
        logger.error(f"Error during Gunicorn files generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_requirements/")
async def generate_requirements_txt(conf: DockerizrConfiguration):
    try:
        logger.debug("Attempting to generate requirements.txt")
        RequirementsAnalyzr(conf).generate_requirements()
        # Assuming the generation was successful, we can send a success message.
        return JSONResponse(
            content={"message": "requirements.txt generated successfully."},
            status_code=200,
        )
    except Exception as e:
        logger.error(f"Error during requirements.txt generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate_dockerfile/")
async def generate_dockerfile(
    conf: DockerizrConfiguration,
):
    try:
        logger.debug("Attempting to generate Dockerfile")
        DockerfileGenerator(conf).generate_dockerfile()
        # Assuming the generation was successful, we can send a success message.
        return JSONResponse(
            content={"message": "Dockerfile generated successfully."},
            status_code=200,
        )
    except Exception as e:
        logger.error(f"Error during Dockefile generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
