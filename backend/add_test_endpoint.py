path = r"C:\Users\KIIT\Downloads\dataiq-platform\dataiqv3\dataiqv3\backend\app\api\v1\endpoints\connections.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Insert new endpoint right before "async def connect_db"
new_endpoint = '''
@router.post("/test-connection")
async def test_connection_endpoint(
    req: ConnectDBRequest,
    ctx: TenantContext = Depends(require_analyst_or_admin),
):
    """Test database credentials without saving the connection."""
    class TempConn:
        pass
    tmp = TempConn()
    tmp.db_type = req.db_type
    tmp.host = req.host
    tmp.port = req.port
    tmp.database = req.database
    tmp.username = req.username
    tmp.encrypted_password = encrypt_credential(req.password)

    ok = connector_service.test_connection(tmp)
    if not ok:
        raise HTTPException(400, "Could not connect to database. Check credentials and network.")
    return {"status": "success", "message": "Connection successful"}


'''

# Find the @router.post("/connect-db" decorator and insert before it
marker = '@router.post("/connect-db"'
if marker in content:
    content = content.replace(marker, new_endpoint + marker, 1)
    print("Added test-connection endpoint!")
else:
    print("ERROR: marker not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)