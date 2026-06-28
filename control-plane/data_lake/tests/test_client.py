from data_lake.client import DataLakeClient
from unittest.mock import MagicMock, patch

def test_data_lake_client_init():
    with patch("hdfs.InsecureClient") as mock_client:
        client = DataLakeClient(url="http://hdfs:9870", user="aop")
        mock_client.assert_called_with("http://hdfs:9870", user="aop")
        assert client.url == "http://hdfs:9870"
        assert client.user == "aop"

def test_data_lake_write_read():
    with patch("hdfs.InsecureClient") as mock_client:
        instance = mock_client.return_value
        
        # Mock reading
        mock_context = MagicMock()
        mock_context.__enter__.return_value.read.return_value = b"test data"
        instance.read.return_value = mock_context
        
        client = DataLakeClient()
        client.write_file("/data/test.txt", b"test data")
        
        instance.write.assert_called_with("/data/test.txt", b"test data", overwrite=True)
        
        data = client.read_file("/data/test.txt")
        assert data == b"test data"

def test_data_lake_list_and_delete():
    with patch("hdfs.InsecureClient") as mock_client:
        instance = mock_client.return_value
        instance.list.return_value = ["file1.txt", "file2.txt"]
        instance.delete.return_value = True
        
        client = DataLakeClient()
        files = client.list_dir("/data")
        
        assert files == ["file1.txt", "file2.txt"]
        instance.list.assert_called_with("/data")
        
        assert client.delete("/data/file1.txt") is True
        instance.delete.assert_called_with("/data/file1.txt", recursive=False)
