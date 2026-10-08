"""Cloud blob storage wrapper."""
class S3Client:
    def upload_file(self, bucket: str, key: str, data: bytes) -> bool:
        return True

    def download_file(self, bucket: str, key: str) -> bytes:
        return b""
