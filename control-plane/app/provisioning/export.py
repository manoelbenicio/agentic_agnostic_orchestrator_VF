import io
import csv
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

# Assuming integration with the repository created earlier
from .repository import ProvisioningRecord, ProvisioningRepository

router = APIRouter(prefix="/provisioning/export", tags=["export"])

# Dummy dependency mapping (would normally be wired to AppState/Dependency Injection)
async def get_provisioning_repository() -> ProvisioningRepository:
    raise NotImplementedError("Dependency not wired to an actual DB pool yet")

def generate_csv_iterator(records: List[ProvisioningRecord]):
    """
    Generator that leverages the native `csv` module to construct
    and yield CSV rows iteratively to a StreamingResponse.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write the CSV Header
    writer.writerow([
        "ID", 
        "Tenant ID", 
        "Resource Type", 
        "Status", 
        "Created At", 
        "Updated At", 
        "Resource Config"
    ])
    yield output.getvalue()
    
    # Reset the buffer
    output.seek(0)
    output.truncate(0)
    
    # Iteratively write rows
    for record in records:
        # Handle datetime formats safely
        created = record.created_at.isoformat() if hasattr(record.created_at, 'isoformat') else str(record.created_at)
        updated = record.updated_at.isoformat() if hasattr(record.updated_at, 'isoformat') else str(record.updated_at)
        
        writer.writerow([
            record.id,
            record.tenant_id,
            record.resource_type,
            record.status,
            created,
            updated,
            str(record.resource_config)
        ])
        
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)


def generate_pdf_html(records: List[ProvisioningRecord]) -> str:
    """
    Constructs a simple HTML string document acting as a printable PDF template.
    In a fully realized environment, this string is passed to a PDF generation
    library like WeasyPrint or pdfkit.
    """
    html = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<title>Provisioning Export</title>",
        "<style>",
        "body { font-family: -apple-system, sans-serif; color: #333; margin: 20px; }",
        "h2 { color: #111; }",
        "table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }",
        "th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }",
        "th { background-color: #f8f9fa; font-weight: 600; }",
        ".status { font-weight: bold; }",
        "</style>",
        "</head>",
        "<body>",
        "<h2>Provisioning Requests Report</h2>",
        "<table>",
        "<tr>",
        "<th>ID</th><th>Tenant ID</th><th>Resource Type</th><th>Status</th><th>Created At</th>",
        "</tr>"
    ]
    
    for record in records:
        created = record.created_at.isoformat() if hasattr(record.created_at, 'isoformat') else str(record.created_at)
        html.append(
            f"<tr>"
            f"<td>{record.id}</td>"
            f"<td>{record.tenant_id}</td>"
            f"<td>{record.resource_type}</td>"
            f"<td class='status'>{record.status}</td>"
            f"<td>{created}</td>"
            f"</tr>"
        )
        
    html.append("</table>")
    html.append("</body>")
    html.append("</html>")
    
    return "".join(html)


@router.get("/csv")
async def export_csv(
    tenant_id: Optional[str] = Query(None, description="Filter export by tenant"),
    status: Optional[str] = Query(None, description="Filter export by status"),
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    """
    Endpoint mapping: GET /provisioning/export/csv
    Streams a CSV file generation row-by-row.
    """
    # Fetch a large bounded slice for export purposes
    records = await repo.list_provisioning_requests(tenant_id=tenant_id, limit=10000, offset=0)
    
    # In-memory filter (mocking DB layer filter)
    if status:
        records = [r for r in records if r.status == status]
        
    response = StreamingResponse(
        generate_csv_iterator(records),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=provisioning_export.csv"
    return response


@router.get("/pdf")
async def export_pdf(
    tenant_id: Optional[str] = Query(None, description="Filter export by tenant"),
    status: Optional[str] = Query(None, description="Filter export by status"),
    repo: ProvisioningRepository = Depends(get_provisioning_repository)
):
    """
    Endpoint mapping: GET /provisioning/export/pdf
    Streams a printable HTML layout designed for PDF saving.
    """
    records = await repo.list_provisioning_requests(tenant_id=tenant_id, limit=10000, offset=0)
    
    if status:
        records = [r for r in records if r.status == status]
        
    html_content = generate_pdf_html(records)
    
    async def stream_html():
        yield html_content.encode("utf-8")
        
    # We serve this as text/html. The user can invoke native Print-to-PDF.
    # Alternatively, passing this output to WeasyPrint transforms it to application/pdf.
    response = StreamingResponse(
        stream_html(),
        media_type="text/html"
    )
    # Using inline so it opens natively for printing instead of downloading obscure HTML
    response.headers["Content-Disposition"] = "inline; filename=provisioning_export_template.html"
    return response
