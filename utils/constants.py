from decimal import Decimal

ALLOWED_FILE_EXTS = ['pdf', 'png', 'svg', 'jpg', 'jpeg', 'docx']

# Gender choices (kept general, but optional for grain app)
CONST_MALE = 'male'
CONST_FEMALE = 'female'

CONST_GENDERS = [
    (CONST_MALE, 'Male'),
    (CONST_FEMALE, 'Female'),
]

# User roles updated for Grain Voucher
USER_ROLE_FARMER = 'farmer'
USER_ROLE_AGENT = 'agent'
USER_ROLE_HUB_ADMIN = 'hub_admin'
USER_ROLE_INVESTOR = 'investor'
USER_ROLE_SUPER_ADMIN = 'super_admin'
USER_ROLE_BDM = 'bdm'
USER_ROLE_CLIENT = 'client'
USER_ROLE_FINANCE = 'finance'

USER_ROLES = [
    (USER_ROLE_FARMER, 'Farmer'),
    (USER_ROLE_AGENT, 'Agent'),
    (USER_ROLE_HUB_ADMIN, 'Hub Admin'),
    (USER_ROLE_INVESTOR, 'Investor'),
    (USER_ROLE_SUPER_ADMIN, 'Super Admin'),
    (USER_ROLE_BDM, 'Business Development Manager'),
    (USER_ROLE_CLIENT, 'Client'),
    (USER_ROLE_FINANCE, 'Finance'),
]

USER_ROLE_KEYS = [
    USER_ROLE_FARMER,
    USER_ROLE_AGENT,
    USER_ROLE_HUB_ADMIN,
    USER_ROLE_INVESTOR,
    USER_ROLE_SUPER_ADMIN,
    USER_ROLE_BDM,
    USER_ROLE_CLIENT,
    USER_ROLE_FINANCE,
]

# User roles for GrainUser model
USER_ROLES = (
    ('farmer', 'Farmer'),
    ('agent', 'Agent'),
    ('hub_admin', 'Hub Admin'),
    ('investor', 'Investor'),
    ('super_admin', 'Super Admin'),
    ('bdm', 'Business Development Manager'),
    ('client', 'Client'),
    ('finance', 'Finance'),

)

USER_ROLE_FARMER = 'farmer'

# Grain types for GrainType model
GRAIN_TYPES = (
    ('maize', 'Maize'),
    ('wheat', 'Wheat'),
    ('rice', 'Rice'),
    ('sorghum', 'Sorghum'),
    ('barley', 'Barley'),
)

# Quality grades for QualityGrade model
QUALITY_GRADES = (
    ('grade_a', 'Grade A (Premium)'),
    ('grade_b', 'Grade B (Standard)'),
    ('grade_c', 'Grade C (Basic)'),
)

VOUCHER_STATUS = [
    ('issued', 'Issued'),
    ('redeemed', 'Redeemed'),
    ('transferred', 'Transferred'),
    ('expired', 'Expired'),
]

TRANSACTION_TYPES = [
    ('deposit', 'Deposit'),
    ('redemption', 'Redemption'),
    ('transfer', 'Transfer'),
    ('purchase', 'Purchase'),
]

TRANSACTION_STATUS = [
    ('pending', 'Pending'),
    ('completed', 'Completed'),
    ('failed', 'Failed'),
    ('cancelled', 'Cancelled'),
]

# Fees (configurable)
ISSUANCE_FEE_RATE = Decimal("0.02")  # 2%
STORAGE_FEE_RATE_PER_MONTH = Decimal("0.005")  # 0.5% per month
REDEMPTION_FEE_RATE = Decimal("0.03")  # 3%
TRADING_FEE_RATE = Decimal("0.01")  # 1%
AGENT_COMMISSION_RATE = Decimal("0.005")  # 0.5%

# File upload settings
ALLOWED_DOCUMENT_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt']
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Currency settings
DEFAULT_CURRENCY = 'UGX'
SUPPORTED_CURRENCIES = [
    ('UGX', 'Ugandan Shilling'),
    ('USD', 'US Dollar'),
    ('EUR', 'Euro'),
    ('GBP', 'British Pound'),
]

# Search and filter settings
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100