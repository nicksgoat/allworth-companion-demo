import { useEffect, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, Chip, Divider, FormControl,
  FormControlLabel, InputLabel, MenuItem, Select, Stack, Step, StepLabel, Stepper,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteForeverOutlinedIcon from '@mui/icons-material/DeleteForeverOutlined';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutlineOutlined';
import type { MonteCarloInputs, MonteCarloResult } from './services/planningApi';

type Row = Record<string, unknown>;

export type PlanningFactsDraft = Record<string, unknown> & {
  name: string;
  people: Row[];
  accounts: Row[];
  liabilities: Row[];
  income: Row[];
  expenses: Row[];
  goals: Row[];
  insurance: Row[];
  real_estate: Row[];
  transfers: Row[];
  assumptions: Row;
};

type Props = {
  facts: Record<string, unknown> | null;
  source: string;
  mcInputs: MonteCarloInputs | null;
  mcResult: MonteCarloResult | null;
  mcRunning: boolean;
  saving: boolean;
  onSave: (draft: PlanningFactsDraft) => Promise<boolean>;
  onRunMonteCarlo: () => Promise<void>;
  onDelete: () => void;
};

const steps = [
  'Household', 'People', 'Assets & debts', 'Income & spending',
  'Goals & protection', 'Assumptions', 'Review & manage',
];

const fields = {
  people: { role: 'client', first_name: '', last_name: '', date_of_birth: '1975-01-01', retirement_age: 65, assumed_age_of_death: 95 },
  accounts: { name: 'New account', kind: 'taxable', value: '0', tax_basis: '0', owner: 'client', growth_rate: '0.05' },
  liabilities: { institution: 'Lender', current_balance: '0', interest_rate: '0.06', term_years: 30 },
  real_estate: { name: 'Primary residence', kind: 'real_estate', value: '0', tax_basis: '0', owner: 'joint', growth_rate: '0.03', liquidity: 5 },
  transfers: { name: 'New transfer', annual_amount: '0', source_account: '', destination_account: '', roth_conversion: false },
  income: { name: 'New income', kind: 'salary', amount: '0', owner: 'client', taxable: true, indexing: { mode: 'inflation' } },
  expenses: { name: 'New expense', kind: 'living', amount: '0', owner: 'client', required: true, indexing: { mode: 'inflation' } },
  goals: {
    name: 'New goal', kind: 'retirement_lifestyle', target_amount: '0',
    target_year: new Date().getFullYear() + 10, priority: 'important',
    importance_group: 'Want',
  },
  insurance: {
    policy_name: 'New policy', policy_number: '', institution: '',
    policy_type: 'term', insured: 'client', owner: 'client',
    beneficiary: '', contingent_beneficiary: '',
    current_death_benefit: '0', current_cash_value: '0', basis: '0',
    cash_value_growth_rate: '0', annual_premium: '0',
    term_years: 20, premium_term_years: 20,
    premium_payer: 'client', under_our_management: false,
    exclude_from_planning: false,
  },
};

const goalKinds = [
  ['retirement_lifestyle', 'Retirement lifestyle'],
  ['essential_retirement_income', 'Essential retirement income'],
  ['healthcare', 'Healthcare / medical'],
  ['long_term_care', 'Long-term care'],
  ['education', 'Education / college'],
  ['wedding', 'Wedding / family event'],
  ['major_purchase', 'Major purchase'],
  ['home_purchase', 'Home purchase / down payment'],
  ['home_remodel', 'Home remodel'],
  ['travel', 'Travel / vacation'],
  ['vehicle', 'Vehicle / boat / RV'],
  ['second_home', 'Second home'],
  ['business', 'Business / startup'],
  ['debt_payoff', 'Debt payoff'],
  ['emergency_reserve', 'Emergency reserve'],
  ['tax_reserve', 'Tax reserve'],
  ['charitable_giving', 'Charitable giving'],
  ['legacy', 'Legacy / bequest'],
  ['dependent_support', 'Dependent or special-needs support'],
  ['elder_care', 'Elder care / family support'],
  ['insurance_protection', 'Insurance / protection funding'],
  ['custom', 'Custom'],
];

const goalPriorities = [
  ['essential', 'Need / essential'],
  ['important', 'Want / important'],
  ['aspirational', 'Wish / aspirational'],
];
const goalImportanceGroups: Record<string, string> = { essential: 'Need', important: 'Want', aspirational: 'Wish' };

function normalizeFacts(value: Record<string, unknown>): PlanningFactsDraft {
  const copy = structuredClone(value) as Record<string, unknown>;
  return {
    ...copy,
    name: String(copy.name || 'Household'),
    people: Array.isArray(copy.people) ? copy.people as Row[] : [],
    accounts: Array.isArray(copy.accounts) ? copy.accounts as Row[] : [],
    liabilities: Array.isArray(copy.liabilities) ? copy.liabilities as Row[] : [],
    income: Array.isArray(copy.income) ? copy.income as Row[] : [],
    expenses: Array.isArray(copy.expenses) ? copy.expenses as Row[] : [],
    goals: Array.isArray(copy.goals) ? copy.goals as Row[] : [],
    insurance: Array.isArray(copy.insurance) ? copy.insurance as Row[] : [],
    real_estate: Array.isArray(copy.real_estate) ? copy.real_estate as Row[] : [],
    transfers: Array.isArray(copy.transfers) ? copy.transfers as Row[] : [],
    assumptions: copy.assumptions && typeof copy.assumptions === 'object' ? copy.assumptions as Row : {},
  };
}

const grid = { display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(4, minmax(0, 1fr))' }, gap: 2 };
const percent = (value: unknown) => Number(value || 0) * 100;
const decimal = (value: string) => String(Number(value || 0) / 100);
const money = (value: unknown) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(Number(value || 0));
const holdingsFor = (account: Row) => Array.isArray(account.holdings) ? account.holdings as Row[] : [];

function Frame({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return <Box><Typography variant="h5">{title}</Typography><Typography color="text.secondary" sx={{ mb: 3 }}>{description}</Typography>{children}</Box>;
}

export default function PlanningInputs({ facts, source, mcInputs, mcResult, mcRunning, saving, onSave, onRunMonteCarlo, onDelete }: Props) {
  const [activeStep, setActiveStep] = useState(0);
  const [draft, setDraft] = useState<PlanningFactsDraft | null>(facts ? normalizeFacts(facts) : null);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setDraft(facts ? normalizeFacts(facts) : null);
    setDirty(false);
  }, [facts]);

  if (!draft) return <Alert severity="info">Household inputs are loading.</Alert>;
  const assetsLocked = source.toLowerCase() === 'datawarehouse';

  const updateRoot = (key: keyof PlanningFactsDraft, value: unknown) => {
    setDraft(current => current ? { ...current, [key]: value } : current);
    setDirty(true);
  };
  const updateRow = (section: 'people' | 'accounts' | 'liabilities' | 'income' | 'expenses' | 'goals' | 'insurance' | 'real_estate' | 'transfers', index: number, key: string, value: unknown) => {
    updateRoot(section, draft[section].map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row));
  };
  const updateGoalPriority = (index: number, value: string) => {
    updateRoot('goals', draft.goals.map((row, rowIndex) => rowIndex === index ? {
      ...row, priority: value, importance_group: goalImportanceGroups[value] || 'Want',
    } : row));
  };
  const addRow = (section: keyof typeof fields) => updateRoot(section, [...draft[section], structuredClone(fields[section])]);
  const removeRow = (section: keyof typeof fields, index: number) => updateRoot(section, draft[section].filter((_, rowIndex) => rowIndex !== index));
  const updateAssumption = (key: string, value: unknown) => updateRoot('assumptions', { ...draft.assumptions, [key]: value });
  const save = async () => { if (await onSave(draft)) setDirty(false); };

  return <Card className="plan-chart-card"><CardContent>
    <Typography variant="h4">Planning Inputs</Typography>
    <Typography color="text.secondary" sx={{ mb: 3 }}>Build the plan one frame at a time. Changes remain a draft until you save and commit a new facts version.</Typography>
    <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4 }}>
      {steps.map(label => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
    </Stepper>

    {activeStep === 0 && <Frame title="Household" description="Confirm the planning household and its warehouse source.">
      <Box sx={grid}><TextField label="Household name" value={draft.name} onChange={event => updateRoot('name', event.target.value)} required />
        <TextField label="Source" value={source || 'planning'} disabled /><TextField label="Household ID" value={String(draft.household_id || '')} disabled /></Box>
    </Frame>}

    {activeStep === 1 && <Frame title="People" description="Add clients, spouses, and other household members. Ages drive retirement, tax, Social Security, RMD, and estate timelines.">
      <Stack sx={{ gap: 2 }}>{draft.people.map((person, index) => <Card variant="outlined" key={String(person.id || index)}><CardContent>
        <Box sx={grid}><FormControl><InputLabel>Role</InputLabel><Select label="Role" value={String(person.role || 'client')} onChange={event => updateRow('people', index, 'role', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="dependent">Dependent</MenuItem><MenuItem value="other">Other</MenuItem></Select></FormControl>
          <TextField label="First name" value={String(person.first_name || '')} onChange={event => updateRow('people', index, 'first_name', event.target.value)} />
          <TextField label="Last name" value={String(person.last_name || '')} onChange={event => updateRow('people', index, 'last_name', event.target.value)} />
          <TextField label="Date of birth" type="date" value={String(person.date_of_birth || '')} onChange={event => updateRow('people', index, 'date_of_birth', event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Retirement age" type="number" value={Number(person.retirement_age || 65)} onChange={event => updateRow('people', index, 'retirement_age', Number(event.target.value))} slotProps={{ htmlInput: { min: 40, max: 90 } }} />
          <TextField label="Assumed age at death" type="number" value={Number(person.assumed_age_of_death || 95)} onChange={event => updateRow('people', index, 'assumed_age_of_death', Number(event.target.value))} slotProps={{ htmlInput: { min: 50, max: 120 } }} />
        </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} disabled={draft.people.length === 1} onClick={() => removeRow('people', index)} sx={{ mt: 2 }}>Remove person</Button>
      </CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('people')} sx={{ mt: 2 }}>Add person</Button>
    </Frame>}

    {activeStep === 2 && <Frame title="Assets & debts" description="Enter investable accounts and liabilities. Warehouse values can be reviewed here without changing the source system.">
      {assetsLocked && <Alert severity="info" sx={{ mb: 2 }}>Connected assets are read-only in the planning tool. Update the relationship source and reconnect to change account values, ownership, type, or holdings.</Alert>}
      <Typography variant="h6" sx={{ mb: 1 }}>Accounts and assets</Typography><Stack sx={{ gap: 2 }}>{draft.accounts.map((account, index) => <Card variant="outlined" key={String(account.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Account name" value={String(account.name || '')} disabled={assetsLocked} onChange={event => updateRow('accounts', index, 'name', event.target.value)} />
        <FormControl disabled={assetsLocked}><InputLabel>Type</InputLabel><Select label="Type" value={String(account.kind || 'taxable')} onChange={event => updateRow('accounts', index, 'kind', event.target.value)}>{['taxable', 'qualified', 'roth', 'cash', '529', 'real_estate', 'private_equity', 'hedge_fund'].map(value => <MenuItem key={value} value={value}>{value.replace('_', ' ')}</MenuItem>)}</Select></FormControl>
        <TextField label="Current value" type="number" value={String(account.value || 0)} disabled={assetsLocked} onChange={event => updateRow('accounts', index, 'value', event.target.value)} />
        <TextField label="Tax basis" type="number" value={String(account.tax_basis || 0)} disabled={assetsLocked} onChange={event => updateRow('accounts', index, 'tax_basis', event.target.value)} />
        <FormControl disabled={assetsLocked}><InputLabel>Owner</InputLabel><Select label="Owner" value={String(account.owner || 'client')} onChange={event => updateRow('accounts', index, 'owner', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="joint">Joint</MenuItem></Select></FormControl>
        <TextField label="Growth rate (%)" type="number" value={percent(account.growth_rate ?? 0.05)} disabled={assetsLocked} onChange={event => updateRow('accounts', index, 'growth_rate', decimal(event.target.value))} />
      </Box>{holdingsFor(account).length > 0 && <Box sx={{ mt: 2 }}>
        <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1, flexWrap: 'wrap' }}>
          <Typography variant="subtitle2">Holdings</Typography>
          <Chip size="small" label={`${holdingsFor(account).length} positions · ${money(holdingsFor(account).reduce((total, holding) => total + Number(holding.market_value || 0), 0))}`} />
        </Stack>
        <Box sx={{ overflowX: 'auto', maxHeight: 280, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow><TableCell>Holding</TableCell><TableCell>Asset class</TableCell><TableCell>Symbol</TableCell><TableCell align="right">Quantity</TableCell><TableCell align="right">Price</TableCell><TableCell align="right">Market value</TableCell><TableCell>As of</TableCell></TableRow></TableHead>
            <TableBody>{holdingsFor(account).map((holding, holdingIndex) => <TableRow key={String(holding.id || holding.cusip || holding.symbol || holdingIndex)}>
              <TableCell>{String(holding.description || 'Holding')}</TableCell>
              <TableCell>{String(holding.asset_class || 'Unclassified')}</TableCell>
              <TableCell>{String(holding.symbol || holding.cusip || '')}</TableCell>
              <TableCell align="right">{Number(holding.quantity || 0).toLocaleString()}</TableCell>
              <TableCell align="right">{money(holding.current_price)}</TableCell>
              <TableCell align="right">{money(holding.market_value)}</TableCell>
              <TableCell>{String(holding.as_of_date || '')}</TableCell>
            </TableRow>)}</TableBody>
          </Table>
        </Box>
      </Box>}<Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} disabled={assetsLocked} onClick={() => removeRow('accounts', index)} sx={{ mt: 2 }}>Remove account</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} disabled={assetsLocked} onClick={() => addRow('accounts')} sx={{ mt: 2 }}>Add account</Button>
      <Divider sx={{ my: 3 }} /><Typography variant="h6" sx={{ mb: 1 }}>Liabilities</Typography><Stack sx={{ gap: 2 }}>{draft.liabilities.map((liability, index) => <Card variant="outlined" key={String(liability.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Lender" value={String(liability.institution || '')} onChange={event => updateRow('liabilities', index, 'institution', event.target.value)} /><TextField label="Current balance" type="number" value={String(liability.current_balance || 0)} onChange={event => updateRow('liabilities', index, 'current_balance', event.target.value)} /><TextField label="Interest rate (%)" type="number" value={percent(liability.interest_rate)} onChange={event => updateRow('liabilities', index, 'interest_rate', decimal(event.target.value))} /><TextField label="Term (years)" type="number" value={Number(liability.term_years || 30)} onChange={event => updateRow('liabilities', index, 'term_years', Number(event.target.value))} />
      </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow('liabilities', index)} sx={{ mt: 2 }}>Remove liability</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('liabilities')} sx={{ mt: 2 }}>Add liability</Button>
      <Divider sx={{ my: 3 }} /><Typography variant="h6" sx={{ mb: 1 }}>Property</Typography><Stack sx={{ gap: 2 }}>{draft.real_estate.map((property, index) => <Card variant="outlined" key={String(property.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Property name" value={String(property.name || '')} onChange={event => updateRow('real_estate', index, 'name', event.target.value)} /><TextField label="Current value" type="number" value={String(property.value || 0)} onChange={event => updateRow('real_estate', index, 'value', event.target.value)} /><TextField label="Cost basis" type="number" value={String(property.tax_basis || 0)} onChange={event => updateRow('real_estate', index, 'tax_basis', event.target.value)} /><TextField label="Appreciation (%)" type="number" value={percent(property.growth_rate)} onChange={event => updateRow('real_estate', index, 'growth_rate', decimal(event.target.value))} />
      </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow('real_estate', index)} sx={{ mt: 2 }}>Remove property</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('real_estate')} sx={{ mt: 2 }}>Add property</Button>
    </Frame>}

    {activeStep === 3 && <Frame title="Income & spending" description="Add annual cash flows. Indexing and detailed timing remain preserved for imported records.">
      {(['income', 'expenses'] as const).map(section => <Box key={section} sx={{ mb: 4 }}><Typography variant="h6" sx={{ mb: 1, textTransform: 'capitalize' }}>{section}</Typography><Stack sx={{ gap: 2 }}>{draft[section].map((flow, index) => <Card variant="outlined" key={String(flow.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Name" value={String(flow.name || '')} onChange={event => updateRow(section, index, 'name', event.target.value)} /><TextField label="Annual amount" type="number" value={String(flow.amount || 0)} onChange={event => updateRow(section, index, 'amount', event.target.value)} />
        <FormControl><InputLabel>Type</InputLabel><Select label="Type" value={String(flow.kind || (section === 'income' ? 'salary' : 'living'))} onChange={event => updateRow(section, index, 'kind', event.target.value)}>{(section === 'income' ? ['salary', 'social_security', 'pension', 'rental', 'other'] : ['living', 'healthcare', 'education', 'housing', 'tax', 'other']).map(value => <MenuItem key={value} value={value}>{value.replace('_', ' ')}</MenuItem>)}</Select></FormControl>
        <FormControl><InputLabel>Owner</InputLabel><Select label="Owner" value={String(flow.owner || 'client')} onChange={event => updateRow(section, index, 'owner', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="joint">Joint</MenuItem></Select></FormControl>
      </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow(section, index)} sx={{ mt: 2 }}>Remove</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow(section)} sx={{ mt: 2 }}>Add {section === 'income' ? 'income' : 'expense'}</Button></Box>)}
      <Divider sx={{ my: 3 }} /><Typography variant="h6" sx={{ mb: 1 }}>Savings & transfers</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>Recurring annual movements between accounts, including Roth conversions.</Typography><Stack sx={{ gap: 2 }}>{draft.transfers.map((transfer, index) => <Card variant="outlined" key={String(transfer.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Name" value={String(transfer.name || '')} onChange={event => updateRow('transfers', index, 'name', event.target.value)} /><TextField label="Annual amount" type="number" value={String(transfer.annual_amount || 0)} onChange={event => updateRow('transfers', index, 'annual_amount', event.target.value)} />
        <FormControl><InputLabel>From account</InputLabel><Select label="From account" value={String(transfer.source_account || '')} onChange={event => updateRow('transfers', index, 'source_account', event.target.value)}><MenuItem value="">(external)</MenuItem>{draft.accounts.map(account => <MenuItem key={String(account.id || account.name)} value={String(account.id || account.name)}>{String(account.name)}</MenuItem>)}</Select></FormControl>
        <FormControl><InputLabel>To account</InputLabel><Select label="To account" value={String(transfer.destination_account || '')} onChange={event => updateRow('transfers', index, 'destination_account', event.target.value)}><MenuItem value="">(external)</MenuItem>{draft.accounts.map(account => <MenuItem key={String(account.id || account.name)} value={String(account.id || account.name)}>{String(account.name)}</MenuItem>)}</Select></FormControl>
      </Box><FormControlLabel control={<Checkbox checked={Boolean(transfer.roth_conversion)} onChange={event => updateRow('transfers', index, 'roth_conversion', event.target.checked)} />} label="Roth conversion" sx={{ mt: 1 }} /><Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow('transfers', index)} sx={{ mt: 1 }}>Remove transfer</Button></Box></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('transfers')} sx={{ mt: 2 }}>Add transfer</Button>
    </Frame>}

    {activeStep === 4 && <Frame title="Goals & protection" description="Capture the outcomes the plan must fund and life-insurance resources available to the household.">
      <Typography variant="h6" sx={{ mb: 1 }}>Goals</Typography><Stack sx={{ gap: 2 }}>{draft.goals.map((goal, index) => <Card variant="outlined" key={String(goal.id || index)}><CardContent><Box sx={grid}>
        <FormControl><InputLabel>Goal type</InputLabel><Select label="Goal type" value={String(goal.kind || 'custom')} onChange={event => updateRow('goals', index, 'kind', event.target.value)}>{goalKinds.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}</Select></FormControl>
        <TextField label="Goal name" value={String(goal.name || '')} onChange={event => updateRow('goals', index, 'name', event.target.value)} />
        <TextField label="Target amount" type="number" value={String(goal.target_amount || 0)} onChange={event => updateRow('goals', index, 'target_amount', event.target.value)} />
        <TextField label="Target year" type="number" value={Number(goal.target_year || new Date().getFullYear())} onChange={event => updateRow('goals', index, 'target_year', Number(event.target.value))} />
        <FormControl><InputLabel>Priority</InputLabel><Select label="Priority" value={String(goal.priority || 'important')} onChange={event => updateGoalPriority(index, event.target.value)}>{goalPriorities.map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}</Select></FormControl>
      </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow('goals', index)} sx={{ mt: 2 }}>Remove goal</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('goals')} sx={{ mt: 2 }}>Add goal</Button>
      <Divider sx={{ my: 3 }} /><Typography variant="h6" sx={{ mb: 1 }}>Life insurance</Typography><Stack sx={{ gap: 2 }}>{draft.insurance.map((policy, index) => <Card variant="outlined" key={String(policy.id || index)}><CardContent><Box sx={grid}>
        <TextField label="Policy name" value={String(policy.policy_name || '')} onChange={event => updateRow('insurance', index, 'policy_name', event.target.value)} />
        <TextField label="Policy number" value={String(policy.policy_number || '')} onChange={event => updateRow('insurance', index, 'policy_number', event.target.value)} />
        <TextField label="Institution" value={String(policy.institution || '')} onChange={event => updateRow('insurance', index, 'institution', event.target.value)} />
        <FormControl><InputLabel>Policy type</InputLabel><Select label="Policy type" value={String(policy.policy_type || 'term')} onChange={event => updateRow('insurance', index, 'policy_type', event.target.value)}>{['term', 'whole_life', 'ul', 'vul', 'vwl', 'group', 'other'].map(value => <MenuItem key={value} value={value}>{value.replace('_', ' ')}</MenuItem>)}</Select></FormControl>
        <FormControl><InputLabel>Insured</InputLabel><Select label="Insured" value={String(policy.insured || 'client')} onChange={event => updateRow('insurance', index, 'insured', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="survivorship">Survivorship</MenuItem></Select></FormControl>
        <FormControl><InputLabel>Owner</InputLabel><Select label="Owner" value={String(policy.owner || 'client')} onChange={event => updateRow('insurance', index, 'owner', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="joint">Joint</MenuItem><MenuItem value="ilit">ILIT</MenuItem><MenuItem value="trust">Trust</MenuItem></Select></FormControl>
        <TextField label="Beneficiary" value={String(policy.beneficiary || '')} onChange={event => updateRow('insurance', index, 'beneficiary', event.target.value)} />
        <TextField label="Contingent beneficiary" value={String(policy.contingent_beneficiary || '')} onChange={event => updateRow('insurance', index, 'contingent_beneficiary', event.target.value)} />
        <TextField label="Death benefit" type="number" value={String(policy.current_death_benefit || 0)} onChange={event => updateRow('insurance', index, 'current_death_benefit', event.target.value)} />
        <TextField label="Cash value" type="number" value={String(policy.current_cash_value || 0)} onChange={event => updateRow('insurance', index, 'current_cash_value', event.target.value)} />
        <TextField label="Basis" type="number" value={String(policy.basis || 0)} onChange={event => updateRow('insurance', index, 'basis', event.target.value)} />
        <TextField label="Cash growth (%)" type="number" value={percent(policy.cash_value_growth_rate)} onChange={event => updateRow('insurance', index, 'cash_value_growth_rate', decimal(event.target.value))} />
        <TextField label="Annual premium" type="number" value={String(policy.annual_premium || 0)} onChange={event => updateRow('insurance', index, 'annual_premium', event.target.value)} />
        <TextField label="Term years" type="number" value={Number(policy.term_years || 0)} onChange={event => updateRow('insurance', index, 'term_years', Number(event.target.value))} />
        <TextField label="Premium term years" type="number" value={Number(policy.premium_term_years || 0)} onChange={event => updateRow('insurance', index, 'premium_term_years', Number(event.target.value))} />
        <FormControl><InputLabel>Premium payer</InputLabel><Select label="Premium payer" value={String(policy.premium_payer || 'client')} onChange={event => updateRow('insurance', index, 'premium_payer', event.target.value)}><MenuItem value="client">Client</MenuItem><MenuItem value="spouse">Spouse</MenuItem><MenuItem value="joint">Joint</MenuItem><MenuItem value="trust">Trust</MenuItem></Select></FormControl>
      </Box><Button color="error" size="small" startIcon={<RemoveCircleOutlineIcon />} onClick={() => removeRow('insurance', index)} sx={{ mt: 2 }}>Remove policy</Button></CardContent></Card>)}</Stack><Button startIcon={<AddIcon />} onClick={() => addRow('insurance')} sx={{ mt: 2 }}>Add policy</Button>
    </Frame>}

    {activeStep === 5 && <Frame title="Planning assumptions" description="Set the shared economic, tax, and projection-horizon assumptions used by every scenario.">
      <Box sx={grid}><TextField label="Start year" type="number" value={Number(draft.assumptions.start_year || new Date().getFullYear())} onChange={event => updateAssumption('start_year', Number(event.target.value))} /><TextField label="Inflation (%)" type="number" value={percent(draft.assumptions.inflation_rate ?? 0.03)} onChange={event => updateAssumption('inflation_rate', decimal(event.target.value))} />
        <FormControl><InputLabel>Tax mode</InputLabel><Select label="Tax mode" value={String(draft.assumptions.tax_mode || 'form_1040')} onChange={event => updateAssumption('tax_mode', event.target.value)}><MenuItem value="form_1040">Form 1040 engine</MenuItem><MenuItem value="flat_tax">Flat tax</MenuItem></Select></FormControl>
        <TextField label="Flat federal tax (%)" type="number" value={percent(draft.assumptions.flat_tax_rate ?? 0.25)} onChange={event => updateAssumption('flat_tax_rate', decimal(event.target.value))} /><TextField label="State tax (%)" type="number" value={percent(draft.assumptions.state_income_tax_rate)} onChange={event => updateAssumption('state_income_tax_rate', decimal(event.target.value))} /><TextField label="Local tax (%)" type="number" value={percent(draft.assumptions.local_income_tax_rate)} onChange={event => updateAssumption('local_income_tax_rate', decimal(event.target.value))} /><TextField label="Save surplus (%)" type="number" value={percent(draft.assumptions.save_pct ?? 1)} onChange={event => updateAssumption('save_pct', decimal(event.target.value))} /><TextField label="Plan end age" type="number" value={Number(draft.assumptions.plan_end_age || 100)} onChange={event => updateAssumption('plan_end_age', Number(event.target.value))} />
      </Box>
    </Frame>}

    {activeStep === 6 && <Frame title="Review & manage" description="Review completeness, commit the facts version, run the plan, or manage the household planning copy.">
      <Stack direction="row" sx={{ gap: 1, flexWrap: 'wrap', mb: 2 }}><Chip color={mcInputs?.ready ? 'success' : 'warning'} label={mcInputs?.ready ? 'Monte Carlo inputs complete' : 'Monte Carlo inputs incomplete'} /><Chip label={`${draft.people.length} people`} /><Chip label={`${draft.accounts.length} accounts`} /><Chip label={`${draft.income.length} income items`} /><Chip label={`${draft.expenses.length} expenses`} /><Chip label={`Holdings: ${mcInputs?.holdings_as_of || 'unavailable'}`} /><Chip label={`CMA: ${mcInputs?.cma_version || 'unavailable'}`} /></Stack>
      {Boolean(mcInputs?.missing_required_inputs.length) && <Alert severity="warning" sx={{ mb: 2 }}>Required before Monte Carlo: {mcInputs?.missing_required_inputs.join(', ')}</Alert>}
      {mcInputs?.warnings.map(message => <Alert key={message} severity="info" sx={{ mb: 1 }}>{message}</Alert>)}
      <Button variant="outlined" onClick={onRunMonteCarlo} disabled={!mcInputs?.ready || mcRunning}>{mcRunning ? 'Running 1,000 trials…' : 'Run Monte Carlo'}</Button>
      {mcResult && <Alert severity="success" sx={{ mt: 2 }}>Probability of success: {(mcResult.probability_of_success * 100).toFixed(1)}% across {mcResult.n_trials.toLocaleString()} trials.</Alert>}
      <Divider sx={{ my: 3 }} /><details><summary>Technical source lineage and facts JSON</summary><pre>{JSON.stringify({ monte_carlo: mcInputs, facts: draft }, null, 2)}</pre></details>
      <Divider sx={{ my: 3 }} /><Box sx={{ p: 2, border: '1px solid', borderColor: 'error.light', borderRadius: 2, bgcolor: '#fff7f7' }}><Stack direction={{ xs: 'column', md: 'row' }} sx={{ gap: 2, alignItems: { md: 'center' }, justifyContent: 'space-between' }}><Box><Typography variant="h6" color="error.main">Household management</Typography><Typography color="text.secondary">Permanently remove this household's planning copy and all related PlanEngine data. Warehouse source records are preserved.</Typography></Box><Button color="error" variant="contained" startIcon={<DeleteForeverOutlinedIcon />} onClick={onDelete} sx={{ flexShrink: 0 }}>Delete household</Button></Stack></Box>
    </Frame>}

    <Divider sx={{ my: 3 }} /><Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
      <Button disabled={activeStep === 0 || saving} onClick={() => setActiveStep(step => step - 1)}>Back</Button>
      <Stack direction="row" sx={{ gap: 1 }}><Button variant="outlined" disabled={!dirty || saving} onClick={save}>{saving ? 'Saving…' : 'Save inputs'}</Button>{activeStep < steps.length - 1 ? <Button variant="contained" onClick={() => setActiveStep(step => step + 1)}>Next</Button> : <Button variant="contained" disabled={!dirty || saving} onClick={save}>{saving ? 'Committing…' : 'Commit planning inputs'}</Button>}</Stack>
    </Stack>
  </CardContent></Card>;
}
