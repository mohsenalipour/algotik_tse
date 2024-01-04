# AlgoTik-tse

[![downloads](https://static.pepy.tech/personalized-badge/algotik-tse?period=total&units=international_system&left_color=black&right_color=green&left_text=Downloads)](https://pepy.tech/project/algotik-tse)
[![PyPI](https://img.shields.io/pypi/v/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/mohsenalipour/algotik_tse/master.svg)](https://results.pre-commit.ci/latest/github/mohsenalipour/algotik_tse/master)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)
[![PyPI - License](https://img.shields.io/pypi/l/algotik-tse.svg)](https://pypi.org/project/algotik-tse/)


<div dir="rtl" align="right">

##### این ماژول جهت مصارف آموزشی، علمی و تحقیقاتی با زبان برنامه نویسی پایتون توسعه یافته است. سعی شده امکاناتی در این ماژول در نظر گرفته شود، که بتواند نیاز به تمامی اطلاعات سازمان بورس را مرتفع نماید و مانند یک وب سرویس دریافت اطلاعات کار کند. خروجی تمامی ساب ماژول ها با فرمت دیتافریم می تواند دریافت گردد.

<p>&nbsp;</p>

#### ویژگی های ماژول:

قابلیت دسترسی به داده‌های یک سهم با استفاده از نماد يا نام کامل فارسی &emsp; <--- &emsp;  <br />
قابلیت انجام تعدیل قیمت به صورت یکجا با احتساب انواع افزایش سرمایه و پرداخت سود نقدی &emsp; <--- &emsp;  <br />
هوشمندی در تشخیص جابجایی یک نماد بین بازارهای مختلف و یکپارچه سازی همه سوابق نمادهای دارای جابجایی &emsp; <---
&emsp;  <br />
قابلیت دسترسی به سوابق همه شاخص‌های بازار بورس و هوشمندی در تشخیص اشتباهات املایی و نگارشی عناوین شاخص صنایع بورسی
&emsp; <--- &emsp;  <br />
قابلیت دسترسی به سابقه داده‌های درون‌روز یک نماد شامل عمق بازار و ریز معاملات &emsp; <--- &emsp;  <br />
قابلیت دسترسی و رصد لحظه‌ای دیده‌بان و عمق بازار در ساعت انجام معاملات در بازار &emsp; <--- &emsp;  <br />
قابلیت تهیه لیست جامعی از مشخصات همه سهم‌های بازار &emsp; <--- &emsp;  <br />
قابلیت دانلود دسته‌جمعی سابقه قیمت لیستی از سهم‌ها و ساخت پنل قیمت پایانی تعدیل شده برای آنها &emsp; <--- &emsp;  <br />
قابلیت دسترسی به سابقه ۱۰ ساله قیمت دلار بازار آزاد &emsp; <--- &emsp;  <br />
خروجی سازگار با دیتافریم پانداز و قابلیت فیلترینگ زمانی مجدد بر اساس تاریخ شمسی &emsp; <--- &emsp;  <br />
قابلیت ارائه تاریخ شمسی، میلادی و نام ایام هفته برای داده‌های روزانه &emsp; <--- &emsp;  <br />

##### همچین می‌توانید از طریق [این لینک](https://t.me/algotik) به آدرس تلگرامی ما دسترسی داشته باشید

##### الهام گرفته شده از finpy-tse و tsemodule5

</div>


<p>&nbsp;</p>
<p>&nbsp;</p>

<div dir="rtl" align="right">

# نصب ماژول

</div>

```python
pip install algotik-tse
```

<p>&nbsp;</p>

<div dir="rtl" align="right">

# آپدیت ماژول

</div>

```python
pip install algotik-tse --upgrade
```

<p>&nbsp;</p>

<div dir="rtl" align="right">

# فراخوانی ماژول

</div>

```python
import algotik_tse as att
```

<p>&nbsp;</p>


<div dir="rtl" align="right">

# دریافت سابقه اطلاعات روزانه یک نماد

<hr style="border:2px solid gray"> </hr>

### دریافت سابقه قیمت:

</div>

```python
att.stock(
    stock='شتران',
    start='1402-01-01',
    end='1402-07-01',
    values=0,
    tse_format=False,
    auto_adjust=True,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    multi_stock_drop=True,
    adjust_volume=False,
    return_type=None,
    )
```
<div dir="rtl">

### دریافت سابقه حقیقی-حقوقی:

</div>

```python
att.stock_RI(
    stock='شتران',
    start='1402-01-01',
    end='1402-07-01',
    values=0,
    tse_format=False,
    output_type="standard",
    date_format="jalali",
    progress=True,
    save_to_file=False,
    multi_stock_drop=True,
    )
```
<div dir="rtl">

### دریافت لیست کلیه دارایی های موجود در بورس تهران:

</div>

```python
att.stocklist(
    bourse=True,
    farabourse=True,
    payeh=True,
    haghe_taqadom=False,
    sandogh=False,
    output="dataframe",
    progress=True
    )
```
<div dir="rtl">

### دریافت اطلاعات مربوط به یک دارایی:

</div>

```python
att.stockdetail(
    stock='شتران'
)
```

<div dir="rtl">

### دریافت لیست سهامداران عمده سهم:

</div>

```python
att.shareholders(
    stock='شتران',
    date=None,
    shh_id=False
)
```
