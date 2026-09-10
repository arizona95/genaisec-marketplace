"""echo-upload-mcp — 업로드 경로 검증용 무해한 stdio MCP 서버."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("echo-upload-mcp")


@mcp.tool()
def echo(text: str) -> str:
    """받은 문자열을 그대로 돌려준다."""
    return text


@mcp.tool()
def count_chars(text: str) -> int:
    """문자열의 글자 수를 센다."""
    return len(text)


if __name__ == "__main__":
    mcp.run()
