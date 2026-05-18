frappe.pages['ai-studio'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'AI Studio',
		single_column: true
	});
	frappe.ai_studio.page = new frappe.ai_studio.AIStudioPage(page);
};
