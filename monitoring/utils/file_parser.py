"""
File Parser for Raw Data Import
Supports both WIDE and LONG format files (CSV/Excel)
"""

import csv
import io
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from django.utils import timezone


class ParsedData:
    """Container for parsed file data"""
    def __init__(self):
        self.format_type: str = ""  # WIDE or LONG
        self.headers: List[str] = []
        self.rows: List[Dict[str, Any]] = []
        self.machine_codes: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.row_count: int = 0
        self.date_range: Tuple[Optional[datetime], Optional[datetime]] = (None, None)
        
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON storage"""
        return {
            'format_type': self.format_type,
            'headers': self.headers,
            'rows': self.rows[:100],  # Store first 100 rows for preview
            'machine_codes': self.machine_codes,
            'warnings': self.warnings,
            'errors': self.errors,
            'row_count': self.row_count,
            'date_range': [
                self.date_range[0].isoformat() if self.date_range[0] else None,
                self.date_range[1].isoformat() if self.date_range[1] else None
            ],
            'total_rows': len(self.rows),
        }


class FileFormatDetector:
    """Detect file format (WIDE vs LONG)"""
    
    @staticmethod
    def detect(headers: List[str]) -> str:
        """
        Detect format based on headers.
        
        WIDE format: Tanggal | Waktu | MachineCode1 | MachineCode2 | ...
        LONG format: Timestamp | Temperature | MachineCode (3 columns)
        """
        if not headers:
            return "UNKNOWN"
        
        # Normalize headers
        normalized = [str(h).strip().lower() for h in headers]
        
        # Check for LONG format (3 columns)
        if len(normalized) == 3:
            # Check if contains timestamp/tanggal, temperature/suhu, machine/code
            has_timestamp = any(kw in normalized[0] for kw in ['timestamp', 'tanggal', 'date', 'time'])
            has_temp = any(kw in normalized[1] for kw in ['temperature', 'suhu', 'temp'])
            has_machine = any(kw in normalized[2] for kw in ['machine', 'code', 'mesin'])
            
            if has_timestamp and has_temp and has_machine:
                return "LONG"
        
        # Check for WIDE format (Tanggal | Waktu | Machine columns)
        if len(normalized) >= 3:
            first_is_date = any(kw in normalized[0] for kw in ['tanggal', 'date', 'tgl'])
            second_is_time = any(kw in normalized[1] for kw in ['waktu', 'time', 'jam'])
            
            if first_is_date and second_is_time:
                return "WIDE"
        
        # Default to WIDE if more than 3 columns
        return "WIDE" if len(normalized) > 3 else "UNKNOWN"


class DateTimeParser:
    """Parse various date and time formats"""
    
    # Date formats (dd/mm/yyyy prioritized)
    DATE_FORMATS = [
        "%d/%m/%Y",      # 25/12/2025
        "%d-%m-%Y",      # 25-12-2025
        "%d/%m/%y",      # 25/12/25
        "%d-%m-%y",      # 25-12-25
        "%Y-%m-%d",      # 2025-12-25
        "%Y/%m/%d",      # 2025/12/25
    ]
    
    # Time formats
    TIME_FORMATS = [
        "%H.%M.%S",      # 10.00.00
        "%H:%M:%S",      # 10:00:00
        "%H.%M",         # 10.00
        "%H:%M",         # 10:00
    ]
    
    # Combined datetime formats
    DATETIME_FORMATS = [
        "%d/%m/%Y %H.%M.%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H.%M.%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%y %H.%M.%S",
        "%d/%m/%y %H:%M:%S",
    ]
    
    @classmethod
    def parse_date(cls, date_str: str) -> Optional[datetime]:
        """Parse date string or datetime object"""
        # If already a datetime object, return it
        if isinstance(date_str, datetime):
            return date_str
        
        date_str = str(date_str).strip()
        if not date_str:
            return None
        
        # Handle Excel datetime strings like "2025-11-19 00:00:00"
        # Extract just the date part if it contains time
        if ' ' in date_str and ':' in date_str:
            # Split and take only date part
            date_part = date_str.split(' ')[0]
            # Try parsing the date part
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(date_part, fmt)
                except (ValueError, TypeError):
                    continue
        
        # Try all date formats
        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        
        return None
    
    @classmethod
    def parse_time(cls, time_str: str) -> Optional[tuple]:
        """Parse time string or time/datetime object, returns (hour, minute, second)"""
        if not time_str:
            return None
        
        # Handle datetime objects (extract time portion)
        if isinstance(time_str, datetime):
            return (time_str.hour, time_str.minute, time_str.second)
        
        # Handle time objects
        from datetime import time as time_type
        if isinstance(time_str, time_type):
            return (time_str.hour, time_str.minute, time_str.second)
        
        time_str = str(time_str).strip()
        
        # Handle datetime strings like "2025-11-19 06:00:00" - extract time part
        if ' ' in time_str and ':' in time_str:
            time_part = time_str.split(' ')[-1]  # Get last part (time)
            time_str = time_part
        
        for fmt in cls.TIME_FORMATS:
            try:
                time_obj = datetime.strptime(time_str, fmt)
                return (time_obj.hour, time_obj.minute, time_obj.second)
            except (ValueError, TypeError):
                continue
        
        return None
    
    @classmethod
    def parse_datetime(cls, datetime_str: str) -> Optional[datetime]:
        """Parse combined datetime string"""
        if isinstance(datetime_str, datetime):
            return datetime_str
        
        datetime_str = str(datetime_str).strip()
        if not datetime_str:
            return None
        
        for fmt in cls.DATETIME_FORMATS:
            try:
                return datetime.strptime(datetime_str, fmt)
            except (ValueError, TypeError):
                continue
        
        return None
    
    @classmethod
    def combine_date_time(cls, date_str: str, time_str: str) -> Optional[datetime]:
        """Combine separate date and time strings"""
        date_obj = cls.parse_date(date_str)
        if not date_obj:
            return None
        
        time_tuple = cls.parse_time(time_str)
        if not time_tuple:
            return None
        
        return date_obj.replace(hour=time_tuple[0], minute=time_tuple[1], second=time_tuple[2])


class WideFormatParser:
    """Parser for wide format files"""
    
    def __init__(self, validate_machines: bool = True):
        self.validate_machines = validate_machines
        self.machine_cache = {}
    
    def parse(self, rows: List[List[Any]], headers: List[str]) -> ParsedData:
        """
        Parse wide format data.
        
        Expected format:
        Tanggal | Waktu | Machine1 | Machine2 | Machine3 | ...
        25/12/2025 | 10.00.00 | 85.5 | 102.0 | 36.0 | ...
        """
        from monitoring.models import Machine
        
        result = ParsedData()
        result.format_type = "WIDE"
        result.headers = headers
        
        if len(headers) < 3:
            result.errors.append("WIDE format requires at least 3 columns (Date, Time, Machine1)")
            return result
        
        # Extract machine codes from headers (column 2 onwards)
        machine_headers = headers[2:]
        result.machine_codes = [str(h).strip() for h in machine_headers]
        
        # Validate machine codes against database
        if self.validate_machines:
            db_machines = Machine.objects.filter(code__in=result.machine_codes).values_list('code', flat=True)
            db_machine_set = set(db_machines)
            
            for code in result.machine_codes:
                if code not in db_machine_set:
                    result.warnings.append(f"Machine code '{code}' not found in database")
                else:
                    self.machine_cache[code] = Machine.objects.get(code=code)
        
        # Parse data rows
        parsed_rows = []
        min_date = None
        max_date = None
        
        for row_idx, row in enumerate(rows, start=2):  # Start at 2 (1 is header)
            if not row or all(x is None or str(x).strip() == '' for x in row):
                continue
            
            try:
                # Parse date and time
                date_str = str(row[0]).strip() if len(row) > 0 else ""
                time_str = str(row[1]).strip() if len(row) > 1 else ""
                
                timestamp = DateTimeParser.combine_date_time(date_str, time_str)
                
                if not timestamp:
                    result.errors.append(f"Row {row_idx}: Invalid date/time format '{date_str}' '{time_str}'")
                    continue
                
                # Track date range
                if min_date is None or timestamp < min_date:
                    min_date = timestamp
                if max_date is None or timestamp > max_date:
                    max_date = timestamp
                
                # Parse temperature values for each machine
                row_data = {
                    'row_number': row_idx,
                    'timestamp': timestamp.isoformat(),
                    'date': date_str,
                    'time': time_str,
                    'machines': {}
                }
                
                for machine_idx, machine_code in enumerate(result.machine_codes):
                    col_idx = machine_idx + 2  # Offset by 2 (date, time)
                    
                    if col_idx >= len(row):
                        row_data['machines'][machine_code] = None
                        continue
                    
                    raw_value = row[col_idx]
                    
                    # Parse temperature
                    try:
                        if raw_value is None or str(raw_value).strip() == '':
                            temp_value = None
                        else:
                            # Check for invalid markers like "--------", "-", etc.
                            raw_str = str(raw_value).strip()
                            # If it's all dashes or single dash, treat as null silently
                            if raw_str == '-' or all(c == '-' for c in raw_str):
                                temp_value = None
                            else:
                                temp_value = float(raw_value)
                    except (ValueError, TypeError):
                        # Silently treat as null (don't log warning for obviously invalid values)
                        temp_value = None
                    
                    row_data['machines'][machine_code] = temp_value
                
                parsed_rows.append(row_data)
                
            except Exception as e:
                result.errors.append(f"Row {row_idx}: {str(e)}")
        
        result.rows = parsed_rows
        result.row_count = len(parsed_rows)
        result.date_range = (min_date, max_date)
        
        return result


class LongFormatParser:
    """Parser for long format files (backward compatibility)"""
    
    def parse(self, rows: List[List[Any]], headers: List[str]) -> ParsedData:
        """
        Parse long format data.
        
        Expected format:
        Timestamp | Temperature | MachineCode
        2025-12-25 10:00:00 | 85.5 | ZET_01
        """
        from monitoring.models import Machine
        
        result = ParsedData()
        result.format_type = "LONG"
        result.headers = headers
        
        if len(headers) != 3:
            result.errors.append("LONG format requires exactly 3 columns")
            return result
        
        # Parse data rows
        parsed_rows = []
        machine_codes_set = set()
        min_date = None
        max_date = None
        
        for row_idx, row in enumerate(rows, start=2):
            if not row or all(x is None or str(x).strip() == '' for x in row):
                continue
            
            try:
                # Parse timestamp
                timestamp_str = str(row[0]).strip() if len(row) > 0 else ""
                timestamp = DateTimeParser.parse_datetime(timestamp_str)
                
                if not timestamp:
                    result.errors.append(f"Row {row_idx}: Invalid timestamp '{timestamp_str}'")
                    continue
                
                # Track date range
                if min_date is None or timestamp < min_date:
                    min_date = timestamp
                if max_date is None or timestamp > max_date:
                    max_date = timestamp
                
                # Parse temperature
                temp_str = row[1] if len(row) > 1 else None
                try:
                    temp_value = float(temp_str) if temp_str else None
                except (ValueError, TypeError):
                    temp_value = None
                
                # Parse machine code
                machine_code = str(row[2]).strip() if len(row) > 2 else ""
                machine_codes_set.add(machine_code)
                
                parsed_rows.append({
                    'row_number': row_idx,
                    'timestamp': timestamp.isoformat(),
                    'temperature': temp_value,
                    'machine_code': machine_code
                })
                
            except Exception as e:
                result.errors.append(f"Row {row_idx}: {str(e)}")
        
        result.rows = parsed_rows
        result.row_count = len(parsed_rows)
        result.machine_codes = sorted(list(machine_codes_set))
        result.date_range = (min_date, max_date)
        
        # Validate machine codes
        db_machines = Machine.objects.filter(code__in=result.machine_codes).values_list('code', flat=True)
        db_machine_set = set(db_machines)
        
        for code in result.machine_codes:
            if code not in db_machine_set:
                result.warnings.append(f"Machine code '{code}' not found in database")
        
        return result


class FileParser:
    """Main file parser that auto-detects format"""
    
    @staticmethod
    def parse_csv(file_obj) -> ParsedData:
        """Parse CSV file"""
        file_data = file_obj.read().decode('utf-8').splitlines()
        reader = csv.reader(file_data)
        
        headers = next(reader, None)
        if not headers:
            result = ParsedData()
            result.errors.append("Empty file or missing header")
            return result
        
        rows = list(reader)
        return FileParser._parse_rows(rows, headers)
    
    @staticmethod
    def parse_excel(file_obj) -> ParsedData:
        """Parse Excel file"""
        try:
            import openpyxl
        except ImportError:
            result = ParsedData()
            result.errors.append("openpyxl library not installed. Cannot process Excel files.")
            return result
        
        wb = openpyxl.load_workbook(file_obj)
        sheet = wb.active
        
        rows_iter = sheet.iter_rows(values_only=True)
        headers = next(rows_iter, None)
        
        if not headers:
            result = ParsedData()
            result.errors.append("Empty file or missing header")
            return result
        
        rows = list(rows_iter)
        return FileParser._parse_rows(rows, list(headers))
    
    @staticmethod
    def _parse_rows(rows: List[List[Any]], headers: List[str]) -> ParsedData:
        """Parse rows with auto-detected format"""
        # Detect format
        format_type = FileFormatDetector.detect(headers)
        
        if format_type == "WIDE":
            parser = WideFormatParser()
            return parser.parse(rows, headers)
        elif format_type == "LONG":
            parser = LongFormatParser()
            return parser.parse(rows, headers)
        else:
            result = ParsedData()
            result.errors.append(f"Unknown file format. Headers: {headers}")
            return result
    
    @staticmethod
    def parse_file(file_obj, filename: str) -> ParsedData:
        """Parse file (auto-detect CSV or Excel)"""
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.csv'):
            return FileParser.parse_csv(file_obj)
        elif filename_lower.endswith('.xlsx') or filename_lower.endswith('.xls'):
            return FileParser.parse_excel(file_obj)
        else:
            result = ParsedData()
            result.errors.append(f"Unsupported file format: {filename}")
            return result
