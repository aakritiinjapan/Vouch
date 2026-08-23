let products = $('.prod-card').toArray().map(item => {
  let $item = $(item);
  
  // Extract name
  let name = $item.find('.prod-card__name').text_sane();
  
  // Extract current price (the actual selling price)
  let price_text = $item.find('.cost-now').text_sane();
  let price_value = parseFloat(price_text.replace(/[^0-9.]/g, ''));
  let currency = price_text.match(/[$€£¥]/)?.[0] || 'USD';
  let price = new Money(price_value, currency);
  
  // Extract original price (may be null)
  let original_price = null;
  let original_price_text = $item.find('.cost-before').text_sane();
  if (original_price_text) {
    let original_price_value = parseFloat(original_price_text.replace(/[^0-9.]/g, ''));
    original_price = new Money(original_price_value, currency);
  }
  
  // Extract shipping cost
  let shipping_text = $item.find('.cost-delivery').text_sane();
  let shipping_value = parseFloat(shipping_text.replace(/[^0-9.]/g, ''));
  let shipping = new Money(shipping_value, currency);
  
  // Extract rating
  let rating = parseFloat($item.find('.stars-value').text_sane());
  
  // Extract stock status
  let stock_element = $item.find('.avail-badge');
  let in_stock = stock_element.hasClass('yes');
  
  return {
    name,
    price,
    original_price,
    shipping,
    rating,
    in_stock
  };
});

return {
  products
};