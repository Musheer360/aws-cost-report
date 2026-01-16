import json
import boto3
import os
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
import base64
from io import BytesIO


def lambda_handler(event, context):
    """
    ExamOnline Budget Breach Analysis Report Generator
    
    Generates a professionally formatted Word document analyzing AWS cost increases
    after a budget threshold has been exceeded.
    """
    allowed_origin = os.environ.get('ALLOWED_ORIGIN', '*')
    
    # Handle CORS preflight
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': allowed_origin,
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    body = json.loads(event['body'])
    months = body['months']
    budget_amount = body.get('budgetAmount', 0)
    breach_date = body.get('breachDate', datetime.now().strftime('%Y-%m-%d'))
    
    # Authentication
    if 'roleArn' in body:
        sts = boto3.client('sts')
        assumed_role = sts.assume_role(
            RoleArn=body['roleArn'],
            RoleSessionName='ExamOnlineBudgetAnalysis'
        )
        session = boto3.Session(
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken'],
            region_name='us-east-1'
        )
    else:
        session = boto3.Session(
            aws_access_key_id=body['accessKeyId'],
            aws_secret_access_key=body['secretAccessKey'],
            region_name=body.get('region', 'us-east-1')
        )
    
    ce = session.client('ce')
    months = sorted(months)
    
    # Convert to month names
    month_names = []
    for month in months:
        dt = datetime.strptime(month, "%Y-%m")
        month_names.append(dt.strftime("%B %Y"))
    
    # Fetch cost data
    service_costs = {}
    regional_costs = {}
    
    for month in months:
        start = f"{month}-01"
        end_date = datetime.strptime(start, "%Y-%m-%d")
        if end_date.month == 12:
            end = f"{end_date.year + 1}-01-01"
        else:
            end = f"{end_date.year}-{str(end_date.month + 1).zfill(2)}-01"
        
        # Get service costs with usage details
        response = ce.get_cost_and_usage(
            TimePeriod={'Start': start, 'End': end},
            Granularity='MONTHLY',
            Metrics=['NetUnblendedCost', 'UsageQuantity'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'},
                {'Type': 'DIMENSION', 'Key': 'USAGE_TYPE'}
            ],
            Filter={'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Tax']}}}
        )
        
        for result in response['ResultsByTime'][0]['Groups']:
            service = result['Keys'][0]
            usage_type = result['Keys'][1]
            cost = float(result['Metrics']['NetUnblendedCost']['Amount'])
            usage = float(result['Metrics']['UsageQuantity']['Amount'])
            
            if cost > 0 or (usage > 0 and is_compute_usage_type(usage_type)):
                if service not in service_costs:
                    service_costs[service] = {}
                if month not in service_costs[service]:
                    service_costs[service][month] = {'total': 0, 'details': []}
                
                service_costs[service][month]['total'] += cost
                service_costs[service][month]['details'].append({
                    'usage_type': usage_type,
                    'cost': cost,
                    'usage': usage
                })
        
        # Get regional costs
        regional_response = ce.get_cost_and_usage(
            TimePeriod={'Start': start, 'End': end},
            Granularity='MONTHLY',
            Metrics=['NetUnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'REGION'}],
            Filter={'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Tax']}}}
        )
        
        for result in regional_response['ResultsByTime'][0]['Groups']:
            region = result['Keys'][0]
            cost = float(result['Metrics']['NetUnblendedCost']['Amount'])
            if cost > 0:
                if region not in regional_costs:
                    regional_costs[region] = {}
                regional_costs[region][month] = cost
    
    # Identify increased cost services only
    increased_services = []
    for service, data in service_costs.items():
        month_costs = [data.get(m, {}).get('total', 0) for m in months]
        if len(month_costs) >= 2:
            rounded_costs = [round(c, 2) for c in month_costs]
            change = rounded_costs[-1] - rounded_costs[0]
            if change > 0:
                pct_change = (change / rounded_costs[0] * 100) if rounded_costs[0] > 0 else 100
                increased_services.append({
                    'service': service,
                    'data': data,
                    'previous_cost': rounded_costs[0],
                    'current_cost': rounded_costs[-1],
                    'change': change,
                    'pct_change': pct_change
                })
    
    increased_services.sort(key=lambda x: x['change'], reverse=True)
    
    # Calculate totals
    overall_previous = round(sum(
        service_costs[s].get(months[0], {}).get('total', 0) for s in service_costs
    ), 2)
    overall_current = round(sum(
        service_costs[s].get(months[-1], {}).get('total', 0) for s in service_costs
    ), 2)
    total_increase = sum(s['change'] for s in increased_services)
    
    # Generate Word Document
    doc = create_formatted_document(
        increased_services, month_names, months, budget_amount,
        breach_date, overall_previous, overall_current, total_increase,
        regional_costs
    )
    
    # Save to bytes
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    report_date = datetime.now().strftime('%Y%m%d')
    filename = f"ExamOnline-Budget-Breach-Analysis-{report_date}.docx"
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': allowed_origin,
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps({
            'file': base64.b64encode(buffer.read()).decode('utf-8'),
            'filename': filename
        })
    }


def create_formatted_document(increased_services, month_names, months, budget_amount,
                               breach_date, overall_previous, overall_current, 
                               total_increase, regional_costs):
    """Create a professionally formatted Word document."""
    doc = Document()
    
    # ===== DOCUMENT SETUP =====
    setup_document(doc)
    
    # ===== COVER PAGE =====
    add_cover_page(doc, month_names, budget_amount, breach_date)
    
    # ===== TABLE OF CONTENTS =====
    add_table_of_contents(doc)
    
    # ===== EXECUTIVE SUMMARY =====
    add_executive_summary(doc, increased_services, month_names, budget_amount,
                          overall_previous, overall_current, total_increase)
    
    # ===== COST DRIVERS ANALYSIS =====
    add_cost_drivers_analysis(doc, increased_services, month_names, total_increase)
    
    # ===== DETAILED SERVICE ANALYSIS =====
    add_detailed_service_analysis(doc, increased_services, month_names, months)
    
    # ===== REGIONAL ANALYSIS =====
    add_regional_analysis(doc, regional_costs, months, month_names)
    
    # ===== RECOMMENDATIONS =====
    add_recommendations(doc, increased_services)
    
    # ===== APPENDIX =====
    add_appendix(doc, increased_services, month_names)
    
    return doc


def setup_document(doc):
    """Configure document settings, margins, and styles."""
    # Set page margins
    for section in doc.sections:
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.54)
        section.right_margin = Cm(2.54)
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
    
    # Configure styles
    styles = doc.styles
    
    # Normal style
    normal = styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    
    # Heading 1
    h1 = styles['Heading 1']
    h1.font.name = 'Calibri Light'
    h1.font.size = Pt(24)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor(0, 51, 102)
    h1.paragraph_format.space_before = Pt(24)
    h1.paragraph_format.space_after = Pt(12)
    h1.paragraph_format.keep_with_next = True
    
    # Heading 2
    h2 = styles['Heading 2']
    h2.font.name = 'Calibri Light'
    h2.font.size = Pt(16)
    h2.font.bold = True
    h2.font.color.rgb = RGBColor(0, 82, 147)
    h2.paragraph_format.space_before = Pt(18)
    h2.paragraph_format.space_after = Pt(8)
    h2.paragraph_format.keep_with_next = True
    
    # Heading 3
    h3 = styles['Heading 3']
    h3.font.name = 'Calibri'
    h3.font.size = Pt(13)
    h3.font.bold = True
    h3.font.color.rgb = RGBColor(0, 102, 153)
    h3.paragraph_format.space_before = Pt(12)
    h3.paragraph_format.space_after = Pt(6)
    h3.paragraph_format.keep_with_next = True


def add_cover_page(doc, month_names, budget_amount, breach_date):
    """Add a professional cover page."""
    # Add spacing at top
    for _ in range(4):
        doc.add_paragraph()
    
    # Company name
    company = doc.add_paragraph()
    company.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = company.add_run('ExamOnline')
    run.font.name = 'Calibri Light'
    run.font.size = Pt(42)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 51, 102)
    
    # Decorative line
    line = doc.add_paragraph()
    line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = line.add_run('━' * 30)
    run.font.color.rgb = RGBColor(0, 102, 153)
    run.font.size = Pt(14)
    
    # Report title
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run('AWS Budget Breach')
    run.font.name = 'Calibri Light'
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(68, 68, 68)
    
    title2 = doc.add_paragraph()
    title2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title2.add_run('Analysis Report')
    run.font.name = 'Calibri Light'
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(68, 68, 68)
    
    doc.add_paragraph()
    
    # Analysis period
    period = doc.add_paragraph()
    period.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = period.add_run('Analysis Period')
    run.font.name = 'Calibri'
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(102, 102, 102)
    
    period_dates = doc.add_paragraph()
    period_dates.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = period_dates.add_run(f'{month_names[0]} — {month_names[-1]}')
    run.font.name = 'Calibri'
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 51, 102)
    
    doc.add_paragraph()
    
    # Budget threshold (if provided)
    if budget_amount > 0:
        budget_label = doc.add_paragraph()
        budget_label.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = budget_label.add_run('Budget Threshold Exceeded')
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(153, 0, 0)
        
        budget_value = doc.add_paragraph()
        budget_value.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = budget_value.add_run(f'${budget_amount:,.2f}')
        run.font.name = 'Calibri'
        run.font.size = Pt(20)
        run.font.bold = True
        run.font.color.rgb = RGBColor(153, 0, 0)
    
    # Add spacing before footer
    for _ in range(6):
        doc.add_paragraph()
    
    # Report date
    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date_para.add_run(f'Report Generated: {datetime.now().strftime("%B %d, %Y")}')
    run.font.name = 'Calibri'
    run.font.size = Pt(11)
    run.font.italic = True
    run.font.color.rgb = RGBColor(102, 102, 102)
    
    # Confidential notice
    conf = doc.add_paragraph()
    conf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    conf.paragraph_format.space_before = Pt(24)
    run = conf.add_run('CONFIDENTIAL')
    run.font.name = 'Calibri'
    run.font.size = Pt(11)
    run.font.bold = True
    run.font.color.rgb = RGBColor(153, 0, 0)
    
    doc.add_page_break()


def add_table_of_contents(doc):
    """Add a table of contents page."""
    toc_heading = doc.add_paragraph()
    run = toc_heading.add_run('Table of Contents')
    run.font.name = 'Calibri Light'
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 51, 102)
    toc_heading.paragraph_format.space_after = Pt(24)
    
    # TOC entries
    toc_entries = [
        ('1.', 'Executive Summary', '3'),
        ('2.', 'Cost Drivers Analysis', '4'),
        ('3.', 'Detailed Service Analysis', '5'),
        ('4.', 'Regional Cost Analysis', '7'),
        ('5.', 'Recommendations', '8'),
        ('6.', 'Appendix: Complete Data', '10'),
    ]
    
    for num, title, page in toc_entries:
        entry = doc.add_paragraph()
        entry.paragraph_format.space_after = Pt(12)
        
        # Number
        run = entry.add_run(f'{num}  ')
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = RGBColor(0, 51, 102)
        
        # Title
        run = entry.add_run(title)
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
        
        # Dots and page number
        run = entry.add_run('  ' + '.' * 60 + '  ')
        run.font.color.rgb = RGBColor(180, 180, 180)
        run.font.size = Pt(10)
        
        run = entry.add_run(page)
        run.font.name = 'Calibri'
        run.font.size = Pt(12)
    
    doc.add_page_break()


def add_executive_summary(doc, increased_services, month_names, budget_amount,
                          overall_previous, overall_current, total_increase):
    """Add executive summary section."""
    doc.add_heading('Executive Summary', level=1)
    
    # Overview box
    add_info_box(doc, 'OVERVIEW', 
        f'This report provides a comprehensive analysis of AWS cost increases between '
        f'{month_names[0]} and {month_names[-1]}. The analysis focuses exclusively on '
        f'services that experienced cost growth, identifying root causes and providing '
        f'actionable recommendations to optimize spending.',
        RGBColor(232, 245, 253))
    
    doc.add_paragraph()
    
    # Key Metrics Section
    doc.add_heading('Key Financial Metrics', level=2)
    
    # Create metrics table
    metrics_table = doc.add_table(rows=2, cols=4)
    metrics_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    format_metrics_table(metrics_table)
    
    # Row 1 - Labels
    labels = ['Previous Period', 'Current Period', 'Total Change', 'Services Impacted']
    for i, label in enumerate(labels):
        cell = metrics_table.rows[0].cells[i]
        cell.text = label
        format_cell(cell, bold=True, bg_color='003366', font_color='FFFFFF', 
                   font_size=10, align='center')
    
    # Row 2 - Values
    overall_change = overall_current - overall_previous
    change_sign = '+' if overall_change >= 0 else ''
    values = [
        f'${overall_previous:,.2f}',
        f'${overall_current:,.2f}',
        f'{change_sign}${overall_change:,.2f}',
        str(len(increased_services))
    ]
    for i, value in enumerate(values):
        cell = metrics_table.rows[1].cells[i]
        cell.text = value
        bg = 'FFE6E6' if i == 2 and overall_change > 0 else 'F5F5F5'
        format_cell(cell, bold=True, bg_color=bg, font_size=14, align='center')
    
    doc.add_paragraph()
    
    # Budget Status (if provided)
    if budget_amount > 0:
        doc.add_heading('Budget Status', level=2)
        
        overage = overall_current - budget_amount
        overage_pct = (overage / budget_amount * 100) if budget_amount > 0 else 0
        
        if overage > 0:
            add_alert_box(doc, '⚠️ BUDGET EXCEEDED',
                f'Current spending of ${overall_current:,.2f} has exceeded the budget '
                f'threshold of ${budget_amount:,.2f} by ${overage:,.2f} ({overage_pct:.1f}%). '
                f'Immediate action is required to identify and address cost drivers.',
                RGBColor(255, 235, 235), RGBColor(153, 0, 0))
        else:
            add_alert_box(doc, '✓ WITHIN BUDGET',
                f'Current spending of ${overall_current:,.2f} is within the budget '
                f'threshold of ${budget_amount:,.2f}.',
                RGBColor(235, 255, 235), RGBColor(0, 102, 0))
        
        doc.add_paragraph()
    
    # Top Cost Drivers Summary
    doc.add_heading('Top 5 Cost Increase Drivers', level=2)
    
    if increased_services[:5]:
        summary_table = doc.add_table(rows=6, cols=5)
        summary_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        format_data_table(summary_table)
        
        # Headers
        headers = ['Service', month_names[0], month_names[-1], 'Increase', '% Change']
        for i, header in enumerate(headers):
            cell = summary_table.rows[0].cells[i]
            cell.text = header
            format_cell(cell, bold=True, bg_color='0052CC', font_color='FFFFFF',
                       font_size=10, align='center')
        
        # Data rows
        for row_idx, svc in enumerate(increased_services[:5], 1):
            row = summary_table.rows[row_idx]
            
            row.cells[0].text = truncate_service_name(svc['service'])
            format_cell(row.cells[0], font_size=10, align='left')
            
            row.cells[1].text = f"${svc['previous_cost']:,.2f}"
            format_cell(row.cells[1], font_size=10, align='right')
            
            row.cells[2].text = f"${svc['current_cost']:,.2f}"
            format_cell(row.cells[2], font_size=10, align='right')
            
            row.cells[3].text = f"${svc['change']:,.2f}"
            format_cell(row.cells[3], font_size=10, align='right', bg_color='FFEEEE')
            
            row.cells[4].text = f"{svc['pct_change']:.1f}%"
            bg = 'FF6666' if svc['pct_change'] > 50 else 'FFCCCC' if svc['pct_change'] > 20 else 'FFE6E6'
            format_cell(row.cells[4], font_size=10, align='center', bg_color=bg, bold=True)
    
    doc.add_page_break()


def add_cost_drivers_analysis(doc, increased_services, month_names, total_increase):
    """Add detailed cost drivers analysis."""
    doc.add_heading('Cost Drivers Analysis', level=1)
    
    intro = doc.add_paragraph()
    intro.add_run(
        'This section provides an in-depth analysis of the primary factors driving '
        'AWS cost increases. Each service is examined to identify root causes and '
        'quantify its contribution to the overall cost growth.'
    )
    intro.paragraph_format.space_after = Pt(16)
    
    # Contribution Analysis
    doc.add_heading('Cost Increase Contribution by Service', level=2)
    
    if increased_services and total_increase > 0:
        # Show top 8 contributors
        top_contributors = increased_services[:8]
        
        contrib_table = doc.add_table(rows=len(top_contributors) + 1, cols=4)
        contrib_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        format_data_table(contrib_table)
        
        headers = ['Service', 'Cost Increase', '% of Total Increase', 'Impact Level']
        for i, header in enumerate(headers):
            cell = contrib_table.rows[0].cells[i]
            cell.text = header
            format_cell(cell, bold=True, bg_color='003366', font_color='FFFFFF',
                       font_size=10, align='center')
        
        for row_idx, svc in enumerate(top_contributors, 1):
            row = contrib_table.rows[row_idx]
            contribution = (svc['change'] / total_increase * 100) if total_increase > 0 else 0
            
            # Determine impact level
            if contribution > 30:
                impact = 'CRITICAL'
                impact_color = 'FF0000'
            elif contribution > 15:
                impact = 'HIGH'
                impact_color = 'FF6600'
            elif contribution > 5:
                impact = 'MEDIUM'
                impact_color = 'FFCC00'
            else:
                impact = 'LOW'
                impact_color = '00CC00'
            
            row.cells[0].text = truncate_service_name(svc['service'])
            format_cell(row.cells[0], font_size=10, align='left')
            
            row.cells[1].text = f"${svc['change']:,.2f}"
            format_cell(row.cells[1], font_size=10, align='right')
            
            row.cells[2].text = f"{contribution:.1f}%"
            format_cell(row.cells[2], font_size=10, align='center')
            
            row.cells[3].text = impact
            format_cell(row.cells[3], font_size=9, align='center', bold=True,
                       font_color=impact_color)
    
    doc.add_paragraph()
    
    # Primary Drivers Detail
    doc.add_heading('Primary Cost Drivers - Detailed Analysis', level=2)
    
    for i, svc in enumerate(increased_services[:5], 1):
        contribution = (svc['change'] / total_increase * 100) if total_increase > 0 else 0
        
        # Service heading
        svc_para = doc.add_paragraph()
        svc_para.paragraph_format.space_before = Pt(16)
        run = svc_para.add_run(f'{i}. {svc["service"]}')
        run.font.bold = True
        run.font.size = Pt(13)
        run.font.color.rgb = RGBColor(0, 51, 102)
        
        # Quick stats in a mini table
        stats_table = doc.add_table(rows=1, cols=4)
        format_inline_stats_table(stats_table)
        
        stats = [
            f"Previous: ${svc['previous_cost']:,.2f}",
            f"Current: ${svc['current_cost']:,.2f}",
            f"Increase: ${svc['change']:,.2f}",
            f"Growth: {svc['pct_change']:.1f}%"
        ]
        for j, stat in enumerate(stats):
            stats_table.rows[0].cells[j].text = stat
            format_cell(stats_table.rows[0].cells[j], font_size=9, align='center',
                       bg_color='F0F5FF')
        
        # Analysis
        driver_analysis = analyze_service_drivers(svc)
        
        analysis_para = doc.add_paragraph()
        analysis_para.paragraph_format.left_indent = Inches(0.25)
        
        run = analysis_para.add_run('Root Cause: ')
        run.font.bold = True
        run.font.size = Pt(10)
        analysis_para.add_run(driver_analysis['primary_driver'])
        
        if driver_analysis['usage_changes']:
            changes_para = doc.add_paragraph()
            changes_para.paragraph_format.left_indent = Inches(0.25)
            run = changes_para.add_run('Key Observations:')
            run.font.bold = True
            run.font.size = Pt(10)
            
            for change in driver_analysis['usage_changes'][:3]:
                bullet = doc.add_paragraph(f'• {change}')
                bullet.paragraph_format.left_indent = Inches(0.5)
                bullet.paragraph_format.space_after = Pt(2)
    
    doc.add_page_break()


def add_detailed_service_analysis(doc, increased_services, month_names, months):
    """Add detailed breakdown for each service."""
    doc.add_heading('Detailed Service Analysis', level=1)
    
    intro = doc.add_paragraph()
    intro.add_run(
        'This section provides a granular breakdown of cost increases for each '
        'impacted AWS service, including specific usage types and resource categories.'
    )
    intro.paragraph_format.space_after = Pt(16)
    
    for svc in increased_services[:10]:  # Top 10 services
        doc.add_heading(truncate_service_name(svc['service']), level=2)
        
        # Cost summary box
        summary = doc.add_paragraph()
        run = summary.add_run(f"${svc['previous_cost']:,.2f}")
        run.font.bold = True
        summary.add_run(f" ({month_names[0]})  →  ")
        run = summary.add_run(f"${svc['current_cost']:,.2f}")
        run.font.bold = True
        summary.add_run(f" ({month_names[-1]})  |  ")
        run = summary.add_run(f"Increase: ${svc['change']:,.2f} ({svc['pct_change']:.1f}%)")
        run.font.bold = True
        run.font.color.rgb = RGBColor(153, 0, 0)
        
        # Usage breakdown
        data = svc['data']
        current_details = data.get(months[-1], {}).get('details', [])
        previous_details = data.get(months[0], {}).get('details', [])
        prev_lookup = {d['usage_type']: d for d in previous_details}
        
        # Find increased usage types
        changes = []
        for detail in current_details:
            usage_type = detail['usage_type']
            current_cost = detail['cost']
            previous_cost = prev_lookup.get(usage_type, {}).get('cost', 0)
            change = current_cost - previous_cost
            if change > 0.01:
                changes.append({
                    'usage_type': usage_type,
                    'previous': previous_cost,
                    'current': current_cost,
                    'change': change
                })
        
        changes.sort(key=lambda x: x['change'], reverse=True)
        
        if changes[:5]:
            doc.add_heading('Usage Type Breakdown', level=3)
            
            usage_table = doc.add_table(rows=min(6, len(changes[:5]) + 1), cols=4)
            format_data_table(usage_table)
            
            headers = ['Usage Type', month_names[0], month_names[-1], 'Change']
            for i, header in enumerate(headers):
                cell = usage_table.rows[0].cells[i]
                cell.text = header
                format_cell(cell, bold=True, bg_color='4A86C7', font_color='FFFFFF',
                           font_size=9, align='center')
            
            for row_idx, change in enumerate(changes[:5], 1):
                row = usage_table.rows[row_idx]
                row.cells[0].text = simplify_usage_type(change['usage_type'])
                format_cell(row.cells[0], font_size=9, align='left')
                
                row.cells[1].text = f"${change['previous']:,.2f}"
                format_cell(row.cells[1], font_size=9, align='right')
                
                row.cells[2].text = f"${change['current']:,.2f}"
                format_cell(row.cells[2], font_size=9, align='right')
                
                row.cells[3].text = f"+${change['change']:,.2f}"
                format_cell(row.cells[3], font_size=9, align='right', bg_color='FFEEEE')
        
        # Reason analysis
        doc.add_heading('Analysis & Root Cause', level=3)
        reason = generate_detailed_reason(svc, changes)
        reason_para = doc.add_paragraph(reason)
        reason_para.paragraph_format.left_indent = Inches(0.25)
        
        doc.add_paragraph()


def add_regional_analysis(doc, regional_costs, months, month_names):
    """Add regional cost breakdown."""
    doc.add_heading('Regional Cost Analysis', level=1)
    
    intro = doc.add_paragraph()
    intro.add_run(
        'This section analyzes cost distribution across AWS regions to identify '
        'geographic patterns in cost increases.'
    )
    intro.paragraph_format.space_after = Pt(16)
    
    # Find regions with increases
    region_changes = []
    for region, costs in regional_costs.items():
        prev = costs.get(months[0], 0)
        curr = costs.get(months[-1], 0)
        change = curr - prev
        if change > 0:
            region_changes.append({
                'region': region,
                'previous': prev,
                'current': curr,
                'change': change
            })
    
    region_changes.sort(key=lambda x: x['change'], reverse=True)
    
    if region_changes:
        doc.add_heading('Regions with Cost Increases', level=2)
        
        table = doc.add_table(rows=len(region_changes) + 1, cols=4)
        format_data_table(table)
        
        headers = ['Region', month_names[0], month_names[-1], 'Increase']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            format_cell(cell, bold=True, bg_color='996600', font_color='FFFFFF',
                       font_size=10, align='center')
        
        for row_idx, rc in enumerate(region_changes, 1):
            row = table.rows[row_idx]
            row.cells[0].text = rc['region']
            format_cell(row.cells[0], font_size=10, align='left')
            
            row.cells[1].text = f"${rc['previous']:,.2f}"
            format_cell(row.cells[1], font_size=10, align='right')
            
            row.cells[2].text = f"${rc['current']:,.2f}"
            format_cell(row.cells[2], font_size=10, align='right')
            
            row.cells[3].text = f"+${rc['change']:,.2f}"
            format_cell(row.cells[3], font_size=10, align='right', bg_color='FFF5E6')
    else:
        doc.add_paragraph('No regions with significant cost increases were identified.')
    
    doc.add_page_break()


def add_recommendations(doc, increased_services):
    """Add recommendations section."""
    doc.add_heading('Recommendations', level=1)
    
    intro = doc.add_paragraph()
    intro.add_run(
        'Based on the analysis of cost increases, the following recommendations '
        'are provided to optimize AWS spending and prevent future budget breaches.'
    )
    intro.paragraph_format.space_after = Pt(16)
    
    # Immediate Actions
    doc.add_heading('Immediate Actions (This Week)', level=2)
    
    immediate = generate_immediate_actions(increased_services)
    for i, action in enumerate(immediate, 1):
        action_para = doc.add_paragraph()
        run = action_para.add_run(f'{i}. {action["title"]}')
        run.font.bold = True
        run.font.color.rgb = RGBColor(153, 0, 0)
        
        desc_para = doc.add_paragraph(action['description'])
        desc_para.paragraph_format.left_indent = Inches(0.25)
        
        if action.get('steps'):
            for step in action['steps']:
                step_para = doc.add_paragraph(f'• {step}')
                step_para.paragraph_format.left_indent = Inches(0.5)
                step_para.paragraph_format.space_after = Pt(2)
    
    doc.add_paragraph()
    
    # Short-term
    doc.add_heading('Short-term Optimizations (1-2 Weeks)', level=2)
    
    short_term = [
        ('Configure Budget Alerts', 
         'Set up AWS Budgets with alerts at 50%, 75%, and 90% thresholds for early warning.'),
        ('Enable Cost Allocation Tags', 
         'Implement mandatory tagging for all resources to enable detailed cost attribution.'),
        ('Review Trusted Advisor', 
         'Check AWS Trusted Advisor for immediate cost optimization recommendations.'),
        ('Audit Unused Resources', 
         'Identify and terminate unused EC2 instances, EBS volumes, and other idle resources.'),
    ]
    
    for title, desc in short_term:
        para = doc.add_paragraph()
        run = para.add_run(f'• {title}: ')
        run.font.bold = True
        para.add_run(desc)
    
    doc.add_paragraph()
    
    # Long-term
    doc.add_heading('Long-term Strategy', level=2)
    
    long_term = [
        ('Implement Savings Plans', 
         'Evaluate workload patterns and purchase Savings Plans for predictable compute usage '
         '(up to 72% savings).'),
        ('Enable Cost Anomaly Detection', 
         'Set up AWS Cost Anomaly Detection for automated alerts on unusual spending patterns.'),
        ('Establish Governance', 
         'Create policies for resource provisioning and establish regular cost review meetings.'),
        ('Right-size Resources', 
         'Use AWS Compute Optimizer to identify and right-size over-provisioned resources.'),
    ]
    
    for title, desc in long_term:
        para = doc.add_paragraph()
        run = para.add_run(f'• {title}: ')
        run.font.bold = True
        para.add_run(desc)
    
    doc.add_page_break()


def add_appendix(doc, increased_services, month_names):
    """Add appendix with complete data."""
    doc.add_heading('Appendix: Complete Cost Increase Data', level=1)
    
    doc.add_paragraph(
        'This appendix contains the complete list of all AWS services with cost '
        'increases during the analysis period, sorted by increase amount.'
    )
    
    if increased_services:
        table = doc.add_table(rows=len(increased_services) + 2, cols=5)
        format_data_table(table)
        
        # Headers
        headers = ['Service', month_names[0], month_names[-1], 'Increase', '% Change']
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            format_cell(cell, bold=True, bg_color='333333', font_color='FFFFFF',
                       font_size=9, align='center')
        
        # Data
        total_prev = 0
        total_curr = 0
        total_change = 0
        
        for row_idx, svc in enumerate(increased_services, 1):
            row = table.rows[row_idx]
            
            row.cells[0].text = truncate_service_name(svc['service'])
            format_cell(row.cells[0], font_size=9, align='left')
            
            row.cells[1].text = f"${svc['previous_cost']:,.2f}"
            format_cell(row.cells[1], font_size=9, align='right')
            
            row.cells[2].text = f"${svc['current_cost']:,.2f}"
            format_cell(row.cells[2], font_size=9, align='right')
            
            row.cells[3].text = f"${svc['change']:,.2f}"
            format_cell(row.cells[3], font_size=9, align='right')
            
            row.cells[4].text = f"{svc['pct_change']:.1f}%"
            format_cell(row.cells[4], font_size=9, align='center')
            
            total_prev += svc['previous_cost']
            total_curr += svc['current_cost']
            total_change += svc['change']
        
        # Totals row
        totals_row = table.rows[-1]
        totals_row.cells[0].text = 'TOTAL'
        format_cell(totals_row.cells[0], bold=True, bg_color='333333', 
                   font_color='FFFFFF', font_size=9, align='left')
        
        totals_row.cells[1].text = f"${total_prev:,.2f}"
        format_cell(totals_row.cells[1], bold=True, bg_color='333333',
                   font_color='FFFFFF', font_size=9, align='right')
        
        totals_row.cells[2].text = f"${total_curr:,.2f}"
        format_cell(totals_row.cells[2], bold=True, bg_color='333333',
                   font_color='FFFFFF', font_size=9, align='right')
        
        totals_row.cells[3].text = f"${total_change:,.2f}"
        format_cell(totals_row.cells[3], bold=True, bg_color='333333',
                   font_color='FFFFFF', font_size=9, align='right')
        
        totals_row.cells[4].text = ''
        format_cell(totals_row.cells[4], bg_color='333333')


# ===== HELPER FUNCTIONS =====

def format_cell(cell, bold=False, bg_color=None, font_color=None, 
                font_size=11, align='left'):
    """Format a table cell with consistent styling."""
    # Set vertical alignment
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    
    # Format paragraph
    for paragraph in cell.paragraphs:
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(4)
        
        if align == 'center':
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == 'right':
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        
        for run in paragraph.runs:
            run.font.name = 'Calibri'
            run.font.size = Pt(font_size)
            run.font.bold = bold
            if font_color:
                # Parse hex color string to RGB
                r = int(font_color[0:2], 16)
                g = int(font_color[2:4], 16)
                b = int(font_color[4:6], 16)
                run.font.color.rgb = RGBColor(r, g, b)
    
    # Set background color
    if bg_color:
        set_cell_shading(cell, bg_color)


def set_cell_shading(cell, color):
    """Set background color for a table cell."""
    shading = OxmlElement('w:shd')
    shading.set(qn('w:fill'), color)
    cell._tc.get_or_add_tcPr().append(shading)


def format_data_table(table):
    """Apply consistent formatting to a data table."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    # Set table borders
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    tblBorders = OxmlElement('w:tblBorders')
    
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:color'), 'CCCCCC')
        tblBorders.append(border)
    
    tblPr.append(tblBorders)
    if tbl.tblPr is None:
        tbl.insert(0, tblPr)


def format_metrics_table(table):
    """Format the key metrics table."""
    format_data_table(table)
    
    # Set column widths
    for row in table.rows:
        for cell in row.cells:
            cell.width = Inches(1.5)


def format_inline_stats_table(table):
    """Format inline statistics table."""
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    
    # Remove borders for inline stats
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement('w:tblPr')
    tblBorders = OxmlElement('w:tblBorders')
    
    for border_name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = OxmlElement(f'w:{border_name}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '2')
        border.set(qn('w:color'), 'DDDDDD')
        tblBorders.append(border)
    
    tblPr.append(tblBorders)
    if tbl.tblPr is None:
        tbl.insert(0, tblPr)


def add_info_box(doc, title, content, bg_color):
    """Add an information box with background."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    
    # Title
    title_para = cell.paragraphs[0]
    run = title_para.add_run(title)
    run.font.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0, 51, 102)
    
    # Content
    content_para = cell.add_paragraph(content)
    content_para.paragraph_format.space_before = Pt(8)
    
    # Background
    set_cell_shading(cell, 'E8F4FC')
    
    # Padding
    cell.paragraphs[0].paragraph_format.space_before = Pt(12)
    cell.paragraphs[-1].paragraph_format.space_after = Pt(12)
    
    for para in cell.paragraphs:
        para.paragraph_format.left_indent = Inches(0.15)
        para.paragraph_format.right_indent = Inches(0.15)


def add_alert_box(doc, title, content, bg_color, title_color):
    """Add an alert box.
    
    Args:
        doc: Document object
        title: Box title text
        content: Box content text
        bg_color: Background color (RGBColor object)
        title_color: Title text color (RGBColor object)
    """
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.rows[0].cells[0]
    
    # Title
    title_para = cell.paragraphs[0]
    run = title_para.add_run(title)
    run.font.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = title_color
    
    # Content
    content_para = cell.add_paragraph(content)
    content_para.paragraph_format.space_before = Pt(8)
    
    # Background color - RGBColor object converts to hex string
    hex_color = str(bg_color)
    set_cell_shading(cell, hex_color)
    
    # Padding
    cell.paragraphs[0].paragraph_format.space_before = Pt(12)
    cell.paragraphs[-1].paragraph_format.space_after = Pt(12)
    
    for para in cell.paragraphs:
        para.paragraph_format.left_indent = Inches(0.15)
        para.paragraph_format.right_indent = Inches(0.15)


def truncate_service_name(name, max_len=40):
    """Truncate long service names."""
    if len(name) <= max_len:
        return name
    return name[:max_len-3] + '...'


def simplify_usage_type(usage_type):
    """Simplify AWS usage type names."""
    if ':' in usage_type:
        parts = usage_type.split(':')
        if len(parts) > 1 and parts[-1]:
            result = parts[-1]
            if len(result) > 35:
                return result[:32] + '...'
            return result
    if len(usage_type) > 35:
        return usage_type[:32] + '...'
    return usage_type


def analyze_service_drivers(svc):
    """Analyze cost drivers for a service."""
    service = svc['service']
    
    result = {
        'primary_driver': 'Increased service usage and resource consumption',
        'usage_changes': [],
        'recommendations': []
    }
    
    if 'EC2' in service:
        result['primary_driver'] = 'Increased compute instance usage, instance type scaling, or extended runtime hours'
        result['usage_changes'] = [
            'Additional EC2 instances provisioned or upgraded to larger instance types',
            'Instances running for extended hours or 24/7 instead of scheduled hours',
            'Data transfer costs associated with EC2 instances increased'
        ]
    elif 'S3' in service:
        result['primary_driver'] = 'Increased storage volume, data transfer, or API request volume'
        result['usage_changes'] = [
            'Storage volume growth from new data uploads',
            'Increased data transfer (cross-region or internet egress)',
            'Higher API request volume (GET, PUT, LIST operations)'
        ]
    elif 'RDS' in service:
        result['primary_driver'] = 'Database instance scaling, storage growth, or increased IOPS'
        result['usage_changes'] = [
            'Database instance upgraded to larger instance class',
            'Storage auto-scaling triggered by data growth',
            'Increased provisioned IOPS or Multi-AZ deployment'
        ]
    elif 'Lambda' in service:
        result['primary_driver'] = 'Increased function invocations, duration, or memory allocation'
        result['usage_changes'] = [
            'Higher number of function invocations from increased traffic',
            'Longer function execution times due to processing complexity',
            'Memory allocation increases affecting cost per invocation'
        ]
    elif 'CloudWatch' in service:
        result['primary_driver'] = 'Increased logging, metrics collection, or dashboard usage'
        result['usage_changes'] = [
            'Log ingestion volume increased significantly',
            'Additional custom metrics or high-resolution metrics enabled',
            'More frequent API calls or additional CloudWatch dashboards'
        ]
    elif 'Transfer' in service or 'CloudFront' in service:
        result['primary_driver'] = 'Increased data transfer volume or CDN usage'
        result['usage_changes'] = [
            'Higher data egress to internet or cross-region',
            'Increased CDN traffic and cache invalidations',
            'Cross-AZ or cross-region data movement increased'
        ]
    else:
        result['usage_changes'] = [
            'Service usage volume increased during the analysis period',
            'Resource configuration changes may have impacted costs',
            'API call volume or data processing increased'
        ]
    
    return result


def generate_detailed_reason(svc, changes):
    """Generate detailed reason for cost increase."""
    service = svc['service']
    pct = svc['pct_change']
    
    if pct > 100:
        severity = 'dramatic'
    elif pct > 50:
        severity = 'significant'
    elif pct > 20:
        severity = 'notable'
    else:
        severity = 'moderate'
    
    reason = f"The {severity} cost increase of {pct:.1f}% for {truncate_service_name(service)} "
    
    if changes:
        top = changes[0]
        reason += f"is primarily attributed to '{simplify_usage_type(top['usage_type'])}', "
        reason += f"which grew from ${top['previous']:,.2f} to ${top['current']:,.2f} "
        reason += f"(+${top['change']:,.2f}). "
    
    if 'EC2' in service:
        reason += "This typically indicates additional compute capacity, larger instances, or extended running hours. "
        reason += "Consider reviewing instance utilization and implementing auto-scaling or scheduled shutdowns."
    elif 'S3' in service:
        reason += "This suggests increased storage consumption or data transfer activity. "
        reason += "Review bucket sizes, implement lifecycle policies, and optimize data transfer patterns."
    elif 'RDS' in service:
        reason += "This may reflect database scaling, storage growth, or IOPS increases. "
        reason += "Evaluate instance right-sizing and consider Reserved Instances for stable workloads."
    elif 'Lambda' in service:
        reason += "This indicates higher function invocations or longer execution times. "
        reason += "Optimize function code and review memory allocation settings."
    else:
        reason += "Review the specific usage patterns for this service to identify optimization opportunities."
    
    return reason


def generate_immediate_actions(increased_services):
    """Generate immediate action recommendations."""
    actions = []
    
    ec2_services = [s for s in increased_services if 'EC2' in s['service']]
    if ec2_services:
        total = sum(s['change'] for s in ec2_services)
        actions.append({
            'title': 'Audit EC2 Instance Usage',
            'description': f'EC2-related costs increased by ${total:,.2f}. Perform immediate review.',
            'steps': [
                'Identify and terminate unused or idle instances',
                'Review instances running outside business hours',
                'Check for over-provisioned instance types'
            ]
        })
    
    storage_services = [s for s in increased_services if 'S3' in s['service'] or 'EBS' in s['service']]
    if storage_services:
        total = sum(s['change'] for s in storage_services)
        actions.append({
            'title': 'Review Storage Resources',
            'description': f'Storage costs increased by ${total:,.2f}. Audit storage utilization.',
            'steps': [
                'Delete unused EBS volumes and old snapshots',
                'Implement S3 lifecycle policies for data archival',
                'Review and remove unnecessary data'
            ]
        })
    
    if not actions and increased_services:
        top = increased_services[0]
        actions.append({
            'title': f'Investigate {truncate_service_name(top["service"])}',
            'description': f'Largest cost increase of ${top["change"]:,.2f}. Requires immediate review.',
            'steps': [
                'Review recent configuration changes',
                'Analyze usage patterns and trends',
                'Identify optimization opportunities'
            ]
        })
    
    return actions


# Compute usage type patterns
COMPUTE_PATTERNS = [
    ('BoxUsage:', 'EC2'),
    ('HeavyUsage:', 'EC2 Reserved'),
    ('SpotUsage:', 'EC2 Spot'),
    ('InstanceUsage:', 'RDS'),
    ('Multi-AZUsage:', 'RDS Multi-AZ'),
    ('ServerlessUsage:', 'RDS Serverless'),
    ('NodeUsage:', 'ElastiCache'),
    ('Node:', 'Redshift'),
]


def is_compute_usage_type(usage_type):
    """Check if usage type is compute resource."""
    for pattern, _ in COMPUTE_PATTERNS:
        if pattern in usage_type:
            return True
    return False
