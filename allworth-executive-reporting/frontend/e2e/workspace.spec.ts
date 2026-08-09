import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
});

test('advisor home uses the governed desktop workspace without overflow', async ({ page }) => {
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Good morning');
  await expect(page.locator('aside.side-nav[aria-label="Primary"]')).toBeVisible();
  await expect(page.getByText('Households to work')).toBeVisible();
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
  expect(dimensions.document).toBe(dimensions.viewport);
});

test('household context survives a copied URL and connects advisor tools', async ({ page }) => {
  await page.getByRole('link', { name: /Evergreen Family/ }).first().click();
  await expect(page).toHaveURL(/household=preview-household/);
  await expect(page.locator('.side-nav-household')).toContainText('Active household');
  await expect(page.getByRole('link', { name: 'Relationship', exact: true })).toHaveAttribute('href', /client=preview-client/);
  const copiedUrl = page.url();
  await page.goto(copiedUrl);
  await expect(page.locator('.side-nav-household')).toContainText('Active household');
});

test('assignment administration excludes unavailable tools', async ({ page }) => {
  await page.goto('/admin');
  await page.getByRole('button', { name: /Assignments/ }).click();
  await expect(page.getByText('Create a governed workspace')).toBeVisible();
  await expect(page.getByText('Heatmaps', { exact: true })).toHaveCount(0);
});

test('every governed home type renders its fixed desktop experience', async ({ page }) => {
  const homes = [
    { type: 'executive', name: 'Executive team', tools: ['executive_report', 'performance', 'brief'], heading: 'Decisions that need your attention' },
    { type: 'operations', name: 'Operations', tools: ['nfbc', 'pipeline_logging', 'file_explorer', 'repcodes'], heading: 'Keep work moving cleanly' },
    { type: 'platform_admin', name: 'Platform Admin', tools: ['admin', 'pipeline_logging', 'sfp2', 'data_catalog'], heading: 'Access, health, and control' },
    { type: 'general', name: 'General workspace', tools: ['crm', 'financial_planning'], heading: 'What do you need to do?' },
  ] as const;

  for (const home of homes) {
    await page.evaluate((assignment) => {
      sessionStorage.setItem('allworth-impersonation', JSON.stringify({
        email: `${assignment.type}@allworth.com`,
        tools: assignment.tools,
        assignment: { id: `${assignment.type}-test`, name: assignment.name, type: assignment.type, home_tool_ids: assignment.tools },
      }));
    }, home);
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(home.heading);
    const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }));
    expect(dimensions.document).toBe(dimensions.viewport);
  }
});
