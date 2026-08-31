"""
PDF Report generation service for candidate pond sites.
"""
from __future__ import annotations

import io
from typing import Any, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def build_candidate_report_pdf(
    village: str,
    candidate: Dict[str, Any],
    catchment: Dict[str, Any],
    rainfall: Dict[str, Any],
    estimate: Dict[str, Any],
) -> bytes:
    """
    Builds a summary dossier PDF report for a recommended candidate pond site.
    """
    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:
        fig, ax = plt.subplots(figsize=(8.5, 11))
        ax.axis("off")

        # Title
        fig.suptitle(
            f"Pond Feasibility Dossier: {village}",
            fontsize=18,
            fontweight="bold",
            y=0.94,
        )

        content_lines = [
            f"Candidate ID: {candidate.get('id', estimate.get('candidate_id', 'N/A'))}",
            f"Location: Lat {candidate.get('lat', 'N/A'):.5f}, Lon {candidate.get('lon', 'N/A'):.5f}",
            f"Terrain Slope: {candidate.get('slope_pct', 'N/A')}%",
            f"Land Classification: {candidate.get('land_type', 'N/A').replace('_', ' ').title()}",
            f"Site Suitability Score: {candidate.get('suitability_score', 'N/A'):.2f} / 1.0",
            "",
            "--- Hydrological & Catchment Metrics ---",
            f"Catchment Basin Area: {catchment.get('area_ha', 'N/A')} ha",
            f"Mean Annual Precipitation: {rainfall.get('mean_annual_mm', 'N/A')} mm",
            f"Rainfall Data Source: {rainfall.get('source', 'N/A')}",
            f"Estimated Harvestable Annual Runoff: {estimate.get('annual_runoff_volume_m3', 'N/A'):,.0f} m³",
            "",
            "--- Recommended Pond Excavation Dimensions ---",
            f"Optimal Water Depth: {estimate.get('recommended_depth_m', 'N/A')} m",
            f"Recommended Surface Area: {estimate.get('recommended_surface_area_m2', 'N/A'):,.1f} m²",
            f"Planned Storage Capacity: {estimate.get('storage_capacity_m3', 'N/A'):,.1f} m³",
            f"Target Capture Efficiency: {estimate.get('capture_efficiency_pct', 'N/A')}%",
            "",
            "--- Engineering Assessment ---",
            f"{estimate.get('justification', 'Site is suitable for natural gravity-fed runoff collection.')}",
        ]

        y_pos = 0.86
        for line in content_lines:
            if line.startswith("---"):
                ax.text(0.1, y_pos, line, fontsize=12, fontweight="bold", color="#1a365d")
            else:
                ax.text(0.12, y_pos, line, fontsize=10.5, color="#2d3748")
            y_pos -= 0.038

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

    buffer.seek(0)
    return buffer.getvalue()
