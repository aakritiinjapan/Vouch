let products = $('.item').toArray().map(item => {
  let $item = $(item);
  
  // Extract name
  let name = $item.find('.item-title').text_sane();
  
  // Extract shipping cost as price (per user request)
  let shipping_text = $item.find('.price-ship').text_sane();
  let price_value = parseFloat(shipping_text.replace(/[^0-9.]/g, ''));
  let currency = shipping_text.match(/[$€£¥]/)?.[0] || 'USD';
  let price = new Money(price_value, currency);
  
  // Extract original price (may be null)
  let original_price = null;
  let original_price_text = $item.find('.price-was').text_sane();
  if (original_price_text) {
    let original_price_value = parseFloat(original_price_text.replace(/[^0-9.]/g, ''));
    original_price = new Money(original_price_value, currency);
  }
  
  // Extract shipping cost
  let shipping = new Money(price_value, currency);
  
  // Extract rating
  let rating = parseFloat($item.find('.rating').text_sane());
  
  // Extract stock status
  let stock_element = $item.find('.stock');
  let in_stock = stock_element.hasClass('in');
  
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