"""Local application entry point."""


def main() -> None:
    import uvicorn

    uvicorn.run("ocean_research_hub.api:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
