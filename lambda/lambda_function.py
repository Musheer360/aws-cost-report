import json
import boto3
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
import base64
from io import BytesIO

def lambda_handler(event, context):
    # Get allowed origin from environment variable
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
    months = body['months']  # Format: ['2025-09', '2025-10']
    client_name = body.get('clientName', 'Client')
    
    # Support both auth methods
    if 'roleArn' in body:
        # Role-based auth
        sts = boto3.client('sts')
        role_arn = body['roleArn']
        assumed_role = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='CostReports360Session'
        )
        session = boto3.Session(
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken'],
            region_name='us-east-1'
        )
    else:
        # Credentials auth
        session = boto3.Session(
            aws_access_key_id=body['accessKeyId'],
            aws_secret_access_key=body['secretAccessKey'],
            region_name=body.get('region', 'us-east-1')
        )
    
    ce = session.client('ce')
    
    # Sort months chronologically (oldest first)
    months = sorted(months)
    
    # Convert to month names
    month_names = []
    month_names_short = []
    for month in months:
        dt = datetime.strptime(month, "%Y-%m")
        month_names.append(dt.strftime("%B %Y"))
        month_names_short.append(dt.strftime("%B"))  # For filename
    
    # Fetch detailed cost data
    service_costs = {}
    regional_costs = {}
    
    for month in months:
        start = f"{month}-01"
        end_date = datetime.strptime(start, "%Y-%m-%d")
        if end_date.month == 12:
            end = f"{end_date.year + 1}-01-01"
        else:
            end = f"{end_date.year}-{str(end_date.month + 1).zfill(2)}-01"
        
        # Get detailed usage data
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
            
            # Include entries with cost > 0, or compute resources with usage > 0
            # This ensures EC2/RDS instances covered by Savings Plans still appear
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
    
    # Sort services by total cost (highest first)
    sorted_services = sorted(
        service_costs.items(),
        key=lambda x: sum(x[1].get(m, {}).get('total', 0) for m in months),
        reverse=True
    )
    
    # Categorize services by cost change
    increased_services = []
    decreased_services = []
    same_services = []
    
    for service, data in sorted_services:
        month_costs = [data.get(m, {}).get('total', 0) for m in months]
        if len(month_costs) >= 2:
            change = month_costs[-1] - month_costs[0]
            
            # Categorize based on actual cost change direction
            # Any increase goes to increased, any decrease goes to decreased
            # Only truly unchanged (change == 0) goes to same
            if change > 0:
                increased_services.append((service, data))
            elif change < 0:
                decreased_services.append((service, data))
            else:
                same_services.append((service, data))
        else:
            same_services.append((service, data))
    
    # Generate Excel
    wb = Workbook()
    
    # Sheet 1: Complete Service Costs
    ws1 = wb.active
    ws1.title = "Complete Service Costs"
    create_service_sheet(ws1, sorted_services, months, month_names)
    
    # Sheet 2: Increased Service Costs
    ws2 = wb.create_sheet("Increased Service Costs")
    create_service_sheet(ws2, increased_services, months, month_names)
    
    # Sheet 3: Decreased Service Costs
    ws3 = wb.create_sheet("Decreased Service Costs")
    create_service_sheet(ws3, decreased_services, months, month_names)
    
    # Sheet 4: Same Service Costs
    ws4 = wb.create_sheet("Same Service Costs")
    create_service_sheet(ws4, same_services, months, month_names)
    
    # Sheet 5: Regional Costs
    ws5 = wb.create_sheet("Per-region Costs")
    create_regional_sheet(ws5, regional_costs, months, month_names)
    
    # Save to bytes
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Format filename: ClientName-Month1-Month2-CostReport.xlsx
    client_name_formatted = client_name.replace(' ', '-')
    months_str = '-'.join(month_names_short)
    filename = f"{client_name_formatted}-{months_str}-CostReport.xlsx"
    
    # Get allowed origin from environment variable
    allowed_origin = os.environ.get('ALLOWED_ORIGIN', '*')
    
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

def create_service_sheet(ws, sorted_services, months, month_names):
    # Styles
    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    blue_fill = PatternFill(start_color="ADD8E6", end_color="ADD8E6", fill_type="solid")
    light_green = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
    light_red = PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid")
    dark_red = PatternFill(start_color="FF6B6B", end_color="FF6B6B", fill_type="solid")
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # Header
    headers = ['Services'] + month_names + ['Service Total', 'Comparison', 'Reason']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(1, col, header)
        cell.fill = yellow_fill
        cell.font = Font(bold=True)
        cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Set header row height
    ws.row_dimensions[1].height = 40
    
    # Data rows
    row = 2
    month_totals = [0.0] * len(months)
    
    for service, data in sorted_services:
        cell = ws.cell(row, 1, service)
        cell.border = border
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        
        month_costs = []
        for col, month in enumerate(months, 2):
            cost = data.get(month, {}).get('total', 0)
            month_costs.append(cost)
            month_totals[col - 2] += cost
            cell = ws.cell(row, col, round(cost, 2))  # Round to 2 decimals for display
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        total = sum(month_costs)
        cell = ws.cell(row, len(months) + 2, round(total, 2))  # Round to 2 decimals
        cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Generate detailed comparison
        comparison = generate_detailed_comparison(month_names, data, months)
        cell = ws.cell(row, len(months) + 3, comparison)
        cell.border = border
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        cell.font = Font(size=10)  # Slightly smaller font for readability
        
        # Generate reason
        reason = generate_detailed_reason(month_names, data, month_costs, months)
        cell = ws.cell(row, len(months) + 4, reason)
        cell.border = border
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        
        # Color coding entire row
        if len(month_costs) >= 2:
            change = month_costs[-1] - month_costs[0]
            # Handle new services (first month = 0) - treat as 100% increase
            if month_costs[0] > 0:
                pct = (change / month_costs[0] * 100)
            elif month_costs[-1] > 0:
                pct = 100  # New service, treat as significant increase
            else:
                pct = 0  # Both zero, no change
            
            # Color based on actual change direction
            if change > 0:
                fill = dark_red if pct > 20 else light_red
            elif change < 0:
                fill = light_green
            else:
                fill = blue_fill  # Only truly unchanged services
            
            for col in range(1, len(months) + 5):
                ws.cell(row, col).fill = fill
        
        # Calculate row height based on the larger of comparison or reason text
        comparison_lines = comparison.count('\n') + 1
        reason_lines = reason.count('\n') + 1
        num_lines = max(comparison_lines, reason_lines)
        ws.row_dimensions[row].height = (num_lines * 15) + 20  # 15 points per line + 20px buffer
        
        row += 1
    
    # Total row
    cell = ws.cell(row, 1, "Total")
    cell.font = Font(bold=True)
    cell.border = border
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    grand_total = 0.0
    for col, total in enumerate(month_totals, 2):
        cell = ws.cell(row, col, round(total, 2))  # Round to 2 decimals
        cell.font = Font(bold=True)
        cell.border = border
        cell.fill = yellow_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        grand_total += total
    
    cell = ws.cell(row, len(months) + 2, round(grand_total, 2))  # Round to 2 decimals
    cell.font = Font(bold=True)
    cell.border = border
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Total comparison and reason - LEFT ALIGNED
    total_comparison = generate_total_comparison(month_names, month_totals)
    cell = ws.cell(row, len(months) + 3, total_comparison)
    cell.border = border
    cell.font = Font(bold=True)
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    
    total_reason = generate_simple_reason(month_totals)
    cell = ws.cell(row, len(months) + 4, total_reason)
    cell.border = border
    cell.font = Font(bold=True)
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    
    # Apply 20px buffer to total row
    num_lines = total_comparison.count('\n') + 1
    ws.row_dimensions[row].height = (num_lines * 15) + 20
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 50
    for col in range(2, len(months) + 3):
        ws.column_dimensions[chr(64 + col)].width = 20
    ws.column_dimensions[chr(64 + len(months) + 3)].width = 50
    ws.column_dimensions[chr(64 + len(months) + 4)].width = 80  # Wider for detailed reasons

def create_regional_sheet(ws, regional_costs, months, month_names):
    # Styles
    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    green_fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
    border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    
    # Header
    headers = ['Region'] + month_names + ['Total']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(1, col, header)
        cell.fill = yellow_fill
        cell.font = Font(bold=True)
        cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Set header row height
    ws.row_dimensions[1].height = 40
    
    # Sort regions by total cost
    sorted_regions = sorted(
        regional_costs.items(),
        key=lambda x: sum(x[1].values()),
        reverse=True
    )
    
    # Data rows
    row = 2
    month_totals = [0.0] * len(months)
    
    for region, costs in sorted_regions:
        region_total = sum(costs.get(month, 0) for month in months)
        
        cell = ws.cell(row, 1, region)
        cell.border = border
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = green_fill
        
        for col, month in enumerate(months, 2):
            cost = costs.get(month, 0)
            month_totals[col - 2] += cost
            cell = ws.cell(row, col, round(cost, 2))  # Round to 2 decimals
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.fill = green_fill
        
        cell = ws.cell(row, len(months) + 2, round(region_total, 2))  # Round to 2 decimals
        cell.border = border
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.fill = green_fill
        
        row += 1
    
    # Total row
    cell = ws.cell(row, 1, "Total")
    cell.font = Font(bold=True)
    cell.border = border
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    grand_total = 0.0
    for col, total in enumerate(month_totals, 2):
        cell = ws.cell(row, col, round(total, 2))  # Round to 2 decimals
        cell.font = Font(bold=True)
        cell.border = border
        cell.fill = yellow_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        grand_total += total
    
    cell = ws.cell(row, len(months) + 2, round(grand_total, 2))  # Round to 2 decimals
    cell.font = Font(bold=True)
    cell.border = border
    cell.fill = yellow_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Adjust column widths
    ws.column_dimensions['A'].width = 30
    for col in range(2, len(months) + 3):
        ws.column_dimensions[chr(64 + col)].width = 15

# Patterns for hourly compute resources
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
    """Check if a usage type is a compute resource (instance hours)"""
    for pattern, _ in COMPUTE_PATTERNS:
        if pattern in usage_type:
            return True
    return False

# Maximum number of items to show in the breakdown
MAX_BREAKDOWN_ITEMS = 5

def format_compute_usage(usage_type, cost, usage):
    """Format compute instance usage with hourly rates"""
    
    for pattern, service_type in COMPUTE_PATTERNS:
        if pattern in usage_type:
            # Extract instance type with error handling for unexpected formats
            try:
                parts = usage_type.split(pattern)
                if len(parts) > 1 and parts[1]:
                    instance_type = parts[1].split(':')[0]
                    # If instance_type is empty after split, use full usage_type
                    if not instance_type:
                        instance_type = usage_type
                else:
                    instance_type = usage_type  # Fallback to full usage type
            except (IndexError, AttributeError):
                instance_type = usage_type  # Fallback to full usage type
            
            # Calculate hourly rate
            if usage > 0:
                hourly_rate = cost / usage
                return f"{instance_type} ({usage:,.3f} Hrs @ ${hourly_rate:.4f}): ${cost:,.2f}"
            else:
                return f"{instance_type}: ${cost:,.2f}"
    
    # Not a compute instance, return standard format
    return None

def generate_detailed_comparison(month_names, data, months):
    lines = []
    
    for i, month in enumerate(months):
        month_data = data.get(month, {})
        
        if 'details' in month_data:
            lines.append(f"\n[{month_names[i].upper()} BREAKDOWN]")
            
            # Separate compute resources from other resources
            compute_details = []
            other_details = []
            for detail in month_data['details']:
                if is_compute_usage_type(detail['usage_type']):
                    compute_details.append(detail)
                else:
                    other_details.append(detail)
            
            # Sort compute resources by usage (hours), others by cost
            compute_details.sort(key=lambda x: x['usage'], reverse=True)
            other_details.sort(key=lambda x: x['cost'], reverse=True)
            
            # Show top compute resources first, then fill remaining slots with other resources
            top_compute = compute_details[:MAX_BREAKDOWN_ITEMS]
            remaining_slots = MAX_BREAKDOWN_ITEMS - len(top_compute)
            top_other = other_details[:remaining_slots] if remaining_slots > 0 else []
            
            sorted_details = top_compute + top_other
            
            for detail in sorted_details:
                # Try to format as compute instance
                formatted = format_compute_usage(detail['usage_type'], detail['cost'], detail['usage'])
                
                if formatted:
                    lines.append(formatted)
                else:
                    # Standard format for non-compute resources
                    lines.append(f"{detail['usage_type']}: USD {detail['cost']:,.2f}")
                    if detail['usage'] > 0:
                        lines.append(f"Usage: {detail['usage']:,.3f} units")
    
    if len(months) >= 2:
        first_total = data.get(months[0], {}).get('total', 0)
        last_total = data.get(months[-1], {}).get('total', 0)
        change = last_total - first_total
        lines.append(f"\n[COST DIFFERENCE]")
        lines.append(f"USD {abs(change):,.2f} ({'Increased' if change > 0 else 'Decreased'})")
    
    return '\n'.join(lines)

def generate_total_comparison(month_names, totals):
    lines = []
    for i, name in enumerate(month_names):
        lines.append(f"{name} Total: USD {totals[i]:,.2f}")
    
    if len(totals) >= 2:
        change = totals[-1] - totals[0]
        lines.append(f"\nTotal Change: USD {abs(change):,.2f} ({'Increased' if change > 0 else 'Decreased'})")
    
    return '\n'.join(lines)

def analyze_usage_patterns(data, months):
    """Analyze usage patterns to identify insights like Savings Plans, Reserved Instances, Free Tier, etc."""
    insights = []
    
    # Collect all details across months
    all_details = {}
    for month in months:
        month_data = data.get(month, {})
        for detail in month_data.get('details', []):
            usage_type = detail['usage_type']
            if usage_type not in all_details:
                all_details[usage_type] = []
            all_details[usage_type].append({
                'month': month,
                'cost': detail['cost'],
                'usage': detail['usage']
            })
    
    # Analyze each usage type for patterns
    for usage_type, records in all_details.items():
        # Check for zero-cost compute resources (Savings Plans/Reserved Instances)
        if is_compute_usage_type(usage_type):
            zero_cost_with_usage = [r for r in records if r['cost'] == 0 and r['usage'] > 0]
            if zero_cost_with_usage:
                # Determine likely coverage type
                if 'HeavyUsage:' in usage_type:
                    coverage = "Reserved Instance"
                elif 'SpotUsage:' in usage_type:
                    coverage = "Spot Instance pricing"
                else:
                    coverage = "Savings Plan or Reserved Instance"
                
                # Extract instance type
                instance_type = usage_type
                for pattern, _ in COMPUTE_PATTERNS:
                    if pattern in usage_type:
                        parts = usage_type.split(pattern)
                        if len(parts) > 1 and parts[1]:
                            instance_type = parts[1].split(':')[0] or usage_type
                        break
                
                total_hours = sum(r['usage'] for r in zero_cost_with_usage)
                insights.append(f"• {instance_type}: {total_hours:,.1f} hours at $0 — covered by {coverage}")
        
        # Check for data transfer patterns
        if 'DataTransfer' in usage_type or 'Bytes' in usage_type:
            costs = [r['cost'] for r in records]
            if len(costs) >= 2 and costs[-1] > costs[0] * 1.5:
                pct_increase = ((costs[-1] - costs[0]) / costs[0] * 100) if costs[0] > 0 else 0
                insights.append(f"• Data transfer ({usage_type.split(':')[-1] if ':' in usage_type else usage_type}) increased by {pct_increase:.0f}%")
        
        # Check for NAT Gateway usage
        if 'NatGateway' in usage_type:
            costs = [r['cost'] for r in records]
            if sum(costs) > 50:  # Significant NAT Gateway cost
                insights.append(f"• NAT Gateway costs are significant — consider VPC endpoints for AWS services")
    
    return insights

def detect_new_or_removed_services(data, months):
    """Detect services that appeared or disappeared between months."""
    insights = []
    
    if len(months) < 2:
        return insights
    
    first_month = months[0]
    last_month = months[-1]
    
    first_types = set(d['usage_type'] for d in data.get(first_month, {}).get('details', []))
    last_types = set(d['usage_type'] for d in data.get(last_month, {}).get('details', []))
    
    # New usage types
    new_types = last_types - first_types
    significant_new = []
    for usage_type in new_types:
        for detail in data.get(last_month, {}).get('details', []):
            if detail['usage_type'] == usage_type and detail['cost'] > 1:
                significant_new.append((usage_type, detail['cost']))
    
    if significant_new:
        significant_new.sort(key=lambda x: x[1], reverse=True)
        for usage_type, cost in significant_new[:2]:
            # Simplify usage type name
            simple_name = usage_type.split(':')[-1] if ':' in usage_type else usage_type
            insights.append(f"• NEW: {simple_name} added (${cost:,.2f})")
    
    # Removed usage types
    removed_types = first_types - last_types
    significant_removed = []
    for usage_type in removed_types:
        for detail in data.get(first_month, {}).get('details', []):
            if detail['usage_type'] == usage_type and detail['cost'] > 1:
                significant_removed.append((usage_type, detail['cost']))
    
    if significant_removed:
        significant_removed.sort(key=lambda x: x[1], reverse=True)
        for usage_type, cost in significant_removed[:2]:
            simple_name = usage_type.split(':')[-1] if ':' in usage_type else usage_type
            insights.append(f"• REMOVED: {simple_name} no longer used (was ${cost:,.2f})")
    
    return insights

def explain_cost_pattern(usage_type, first_cost, last_cost, first_usage, last_usage):
    """Generate a human-readable explanation for a cost change."""
    diff = last_cost - first_cost
    
    # Check for Free Tier patterns
    if 'Free' in usage_type or (first_cost == 0 and last_cost == 0):
        return "Free tier usage"
    
    # Check for compute with pricing changes
    if is_compute_usage_type(usage_type):
        if first_usage > 0 and last_usage > 0:
            # Both first_usage and last_usage are > 0, safe to divide
            first_rate = first_cost / first_usage
            last_rate = last_cost / last_usage
            
            if abs(first_rate - last_rate) > 0.001:
                if last_cost == 0 and last_usage > 0:
                    return "Now covered by Savings Plan/RI"
                elif first_cost == 0 and first_usage > 0:
                    return "Savings Plan/RI coverage ended"
                elif last_rate < first_rate:
                    return "Better pricing (Savings Plan/RI applied)"
                else:
                    return "Rate increased"
            
            usage_diff = last_usage - first_usage
            if abs(usage_diff) > first_usage * 0.1:
                if usage_diff > 0:
                    return f"Usage increased ({usage_diff:,.0f} more hours)"
                else:
                    return f"Usage decreased ({abs(usage_diff):,.0f} fewer hours)"
    
    # Storage patterns
    if 'Storage' in usage_type or 'TimedStorage' in usage_type:
        if diff > 0:
            return "Storage growth"
        else:
            return "Storage reduced or cleaned up"
    
    # Data transfer patterns
    if 'DataTransfer' in usage_type or 'Bytes' in usage_type:
        if diff > 0:
            return "Increased data transfer"
        else:
            return "Reduced data transfer"
    
    # API/Request patterns
    if 'Request' in usage_type or 'API' in usage_type or 'Invocation' in usage_type:
        if diff > 0:
            return "Higher API/request volume"
        else:
            return "Lower API/request volume"
    
    # Default explanation based on direction
    if diff > 0:
        return "Usage increased"
    elif diff < 0:
        return "Usage decreased"
    else:
        return "No change"

def generate_detailed_reason(month_names, data, month_costs, months):
    if len(month_costs) < 2:
        return "Insufficient data for comparison"
    
    change = month_costs[-1] - month_costs[0]
    pct = (change / month_costs[0] * 100) if month_costs[0] > 0 else (100 if month_costs[-1] > 0 else 0)
    
    lines = []
    
    # Overall change summary
    if abs(pct) < 5:
        lines.append("Minimal cost difference (within 5%)")
    elif change > 0:
        lines.append(f"Cost increased by ${abs(change):,.2f} ({abs(pct):.1f}%)")
    else:
        lines.append(f"Cost decreased by ${abs(change):,.2f} ({abs(pct):.1f}%)")
    
    # Get detailed analysis
    first_month = months[0]
    last_month = months[-1]
    
    # Create lookup for usage data
    first_data = {d['usage_type']: d for d in data.get(first_month, {}).get('details', [])}
    last_data = {d['usage_type']: d for d in data.get(last_month, {}).get('details', [])}
    
    # Analyze top changes with explanations
    changes = []
    all_types = set(first_data.keys()) | set(last_data.keys())
    
    for usage_type in all_types:
        first_detail = first_data.get(usage_type, {'cost': 0, 'usage': 0})
        last_detail = last_data.get(usage_type, {'cost': 0, 'usage': 0})
        
        first_cost = first_detail['cost'] if isinstance(first_detail, dict) else first_detail
        last_cost = last_detail['cost'] if isinstance(last_detail, dict) else last_detail
        first_usage = first_detail.get('usage', 0) if isinstance(first_detail, dict) else 0
        last_usage = last_detail.get('usage', 0) if isinstance(last_detail, dict) else 0
        
        if first_cost > 0 or last_cost > 0 or (is_compute_usage_type(usage_type) and (first_usage > 0 or last_usage > 0)):
            diff = last_cost - first_cost
            explanation = explain_cost_pattern(usage_type, first_cost, last_cost, first_usage, last_usage)
            # Track if this is a Savings Plan related change for filtering
            is_savings_plan_related = explanation and ('Savings Plan' in explanation or 'RI' in explanation)
            changes.append((usage_type, diff, first_cost, last_cost, explanation, is_savings_plan_related))
    
    changes.sort(key=lambda x: abs(x[1]), reverse=True)
    
    # Add top changes with explanations - include significant cost changes and savings plan related items
    significant_changes = [c for c in changes[:4] if abs(c[1]) > 0.01 or c[5]]
    
    if significant_changes:
        lines.append("\n[KEY DRIVERS]")
        for usage_type, diff, first, last, explanation, _ in significant_changes:
            # Simplify usage type name
            simple_name = usage_type
            for pattern, _ in COMPUTE_PATTERNS:
                if pattern in usage_type:
                    parts = usage_type.split(pattern)
                    if len(parts) > 1 and parts[1]:
                        extracted = parts[1].split(':')[0]
                        simple_name = extracted if extracted else usage_type
                    break
            if ':' in simple_name and simple_name == usage_type:
                simple_name = usage_type.split(':')[-1]
            
            direction = "↑" if diff > 0 else "↓" if diff < 0 else "→"
            lines.append(f"• {simple_name}: ${first:,.2f} {direction} ${last:,.2f}")
            lines.append(f"  Why: {explanation}")
    
    # Add special insights
    insights = analyze_usage_patterns(data, months)
    new_removed = detect_new_or_removed_services(data, months)
    
    all_insights = insights + new_removed
    if all_insights:
        lines.append("\n[INSIGHTS]")
        for insight in all_insights[:4]:  # Limit to 4 insights
            lines.append(insight)
    
    # Add recommendations for significant cost increases
    if change > 100:
        lines.append("\n[RECOMMENDATIONS]")
        
        # Check for potential savings
        has_compute = any(is_compute_usage_type(d['usage_type']) 
                        for d in data.get(last_month, {}).get('details', [])
                        if d['cost'] > 0)
        
        has_data_transfer = any('DataTransfer' in d['usage_type'] or 'Bytes' in d['usage_type']
                               for d in data.get(last_month, {}).get('details', [])
                               if d['cost'] > 10)
        
        has_nat = any('NatGateway' in d['usage_type']
                     for d in data.get(last_month, {}).get('details', [])
                     if d['cost'] > 20)
        
        if has_compute:
            lines.append("• Consider Savings Plans or Reserved Instances for steady compute workloads")
        if has_data_transfer:
            lines.append("• Review data transfer patterns; consider CloudFront or VPC endpoints")
        if has_nat:
            lines.append("• NAT Gateway costs are high; evaluate VPC endpoints for AWS services")
    
    return '\n'.join(lines)

def generate_simple_reason(costs):
    if len(costs) < 2:
        return "Insufficient data"
    
    change = costs[-1] - costs[0]
    pct = (change / costs[0] * 100) if costs[0] > 0 else 0
    
    if abs(pct) < 5:
        return "Minimal Cost Difference"
    elif change > 0:
        return f"Cost increased by USD {abs(change):,.2f} ({abs(pct):.1f}% increase)"
    else:
        return f"Cost decreased by USD {abs(change):,.2f} ({abs(pct):.1f}% decrease)"
